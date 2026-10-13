# Derived from Stanford OVAL STORM fb951af7744dab086e34962e9bc6fe878e145f83 (MIT; see LICENSE).
from .. import prompting as dspy
import os
from dataclasses import dataclass, field, asdict
from typing import List, Union, Literal, Optional, Dict

from .modules import collaborative_storm_utils as collaborative_storm_utils
from .modules.callback import BaseCallbackHandler
from .modules.co_storm_agents import (
    SimulatedUser,
    PureRAGAgent,
    Moderator,
    CoStormExpert,
)
from .modules.expert_generation import GenerateExpertModule
from .modules.warmstart_hierarchical_chat import WarmStartModule
from ..dataclass import ConversationTurn, KnowledgeBase
from ..vectors import LocalEncoder as Encoder
from ..interface import LMConfigs, Agent
from ..logging_wrapper import LoggingWrapper


class CollaborativeStormLMConfigs(LMConfigs):
    """Configurations for LLM used in different parts of Co-STORM.

    Given that different parts in Co-STORM framework have different complexity, we use different LLM configurations
    to achieve a balance between quality and efficiency. If no specific configuration is provided, we use the default
    setup in the paper.
    """

    def __init__(self):
        self.question_answering_lm = None
        self.discourse_manage_lm = None
        self.utterance_polishing_lm = None
        self.warmstart_outline_gen_lm = None
        self.question_asking_lm = None
        self.knowledge_base_lm = None

    def init(self, *args, **kwargs):
        raise ValueError("Co-STORM requires explicit local application LM adapters")

    def set_question_answering_lm(self, model: Union[dspy.dsp.LM, dspy.dsp.HFModel]):
        self.question_answering_lm = model

    def set_discourse_manage_lm(self, model: Union[dspy.dsp.LM, dspy.dsp.HFModel]):
        self.discourse_manage_lm = model

    def set_utterance_polishing_lm(self, model: Union[dspy.dsp.LM, dspy.dsp.HFModel]):
        self.utterance_polishing_lm = model

    def set_warmstart_outline_gen_lm(self, model: Union[dspy.dsp.LM, dspy.dsp.HFModel]):
        self.warmstart_outline_gen_lm = model

    def set_question_asking_lm(self, model: Union[dspy.dsp.LM, dspy.dsp.HFModel]):
        self.question_asking_lm = model

    def set_knowledge_base_lm(self, model: Union[dspy.dsp.LM, dspy.dsp.HFModel]):
        self.knowledge_base_lm = model

    def collect_and_reset_lm_usage(self):
        lm_usage = {}
        for attr_name in self.__dict__:
            if "_lm" in attr_name and hasattr(
                getattr(self, attr_name), "get_usage_and_reset"
            ):
                usage = getattr(self, attr_name).get_usage_and_reset()
                if any(
                    value["prompt_tokens"] != 0 or value["completion_tokens"] != 0
                    for value in usage.values()
                ):
                    lm_usage[attr_name] = usage
        return lm_usage

    def to_dict(self):
        """
        Converts the CollaborativeStormLMConfigs instance to a dictionary representation.

        Returns:
            dict: The dictionary representation of the CollaborativeStormLMConfigs.
        """
        config_dict = {}
        for attr_name in self.__dict__:
            config_dict[attr_name] = getattr(self, attr_name).kwargs
        return config_dict


@dataclass
class RunnerArgument:
    """Arguments for controlling the STORM Wiki pipeline."""

    topic: str = field(
        metadata={"help": "Topic of discourse"},
    )
    retrieve_top_k: int = field(
        default=10,
        metadata={"help": "retrieve top k results for each query in retriever"},
    )
    max_search_queries: int = field(
        default=2,
        metadata={
            "help": "Maximum number of search queries to consider for each question."
        },
    )
    total_conv_turn: int = field(
        default=20,
        metadata={"help": "Maximum number turn in conversation."},
    )
    max_search_thread: int = field(
        default=5,
        metadata={"help": "Maximum number of parallel thread for retriever"},
    )
    max_search_queries_per_turn: int = field(
        default=3,
        metadata={"help": "Maximum number of search queries to consider in each turn."},
    )
    warmstart_max_num_experts: int = field(
        default=3,
        metadata={
            "help": "Max number of experts in perspective guided QA in warm start process"
        },
    )
    warmstart_max_turn_per_experts: int = field(
        default=2,
        metadata={"help": "Max number of turns per perspective in warm start process"},
    )
    warmstart_max_thread: int = field(
        default=3,
        metadata={
            "help": "Max number thread for parallel perspective guided QA in warm start process"
        },
    )
    max_thread_num: int = field(
        default=10,
        metadata={
            "help": "Maximum number of threads to use. "
            "Consider reducing it if keep getting 'Exceed rate limit' error when calling LM API."
        },
    )
    max_num_round_table_experts: int = field(
        default=2,
        metadata={"help": "Max number of active experts in round table discussion."},
    )
    moderator_override_N_consecutive_answering_turn: int = field(
        default=3,
        metadata={
            "help": "Number of consecutive experts answering turn before moderator override the conversation"
        },
    )
    node_expansion_trigger_count: int = field(
        default=10,
        metadata={
            "help": "Trigger node expansion for node that contain more than N snippets"
        },
    )
    disable_moderator: bool = field(
        default=False,
        metadata={"help": "If True, disable moderator."},
    )
    disable_multi_experts: bool = field(
        default=False,
        metadata={"help": "If True, disable moderator."},
    )
    rag_only_baseline_mode: bool = field(
        default=False,
        metadata={"help": "If True, switch to rag online baseline mode"},
    )

    def to_dict(self):
        """
        Converts the RunnerArgument instance to a dictionary representation.

        Returns:
            dict: The dictionary representation of the RunnerArgument.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, *args, **kwargs):
        raise ValueError("Restore through the application with explicit adapters")

    def warm_start(self):
        """
        Warm start co-storm system to conduct background information search in order to build shared conceptual space with user.
        This stage is a mini-STORM, spawning multiple LLM agent with different perspective and perform multi-round conversation.
        The knowledge base (i.e. mind map) will be initialize using the collected information.

        It will also generate a first draft of report and use it to produce an engaging and concise conversation presented to the
        user to catch up with system's knowledge about the topic.
        """
        with self.logging_wrapper.log_pipeline_stage(
            pipeline_stage=f"warm start stage"
        ):
            if not self.runner_argument.rag_only_baseline_mode:
                warm_start_module = WarmStartModule(
                    lm_config=self.lm_config,
                    runner_argument=self.runner_argument,
                    logging_wrapper=self.logging_wrapper,
                    rm=self.rm,
                    callback_handler=self.callback_handler,
                )

                (
                    warmstart_conv,
                    warmstart_revised_conv,
                    warmstart_experts,
                ) = warm_start_module.initiate_warm_start(
                    topic=self.runner_argument.topic,
                    knowledge_base=self.knowledge_base,
                )
                self.discourse_manager.experts = (
                    self.discourse_manager._parse_expert_names_to_agent(
                        warmstart_experts
                    )
                )
                self.discourse_manager.next_turn_moderator_override = True
                self.conversation_history = (
                    warmstart_revised_conv if warmstart_revised_conv else warmstart_conv
                )
                self.warmstart_conv_archive = warmstart_conv
                self.knowledge_base.reorganize()
            else:
                if self.knowledge_base is None:
                    self.knowledge_base = KnowledgeBase(
                        topic=self.runner_argument.topic,
                        knowledge_base_lm=self.lm_config.knowledge_base_lm,
                        node_expansion_trigger_count=self.runner_argument.node_expansion_trigger_count,
                        encoder=self.encoder,
                    )
                if self.conversation_history is None:
                    self.conversation_history = []
                conv_turn = (
                    self.discourse_manager.pure_rag_agent.generate_topic_background()
                )
                self.conversation_history.append(conv_turn)
                self.knowledge_base.update_from_conv_turn(
                    conv_turn=conv_turn,
                    allow_create_new_node=True,
                    insert_under_root=self.runner_argument.rag_only_baseline_mode,
                )

    def generate_report(self) -> str:
        """
        Generate report leveraging organized collected information in the knowledge base (i.e. mind map).
        The article generation follows the paradigm in STORM paper, where it considers mind map nodes as section names, and generate the report section by section.

        Returns:
            str: A string representing the report, with "#" "##" indicating hierarchical sections and [1][2] indicating references.
        """
        with self.logging_wrapper.log_pipeline_stage(
            f"report generation after conv turn: {len(self.conversation_history)}"
        ):
            with self.logging_wrapper.log_event(
                "report generation stage: generate report"
            ):
                return self.knowledge_base.to_report()

    def dump_logging_and_reset(self):
        return self.logging_wrapper.dump_logging_and_reset()

    def step(
        self,
        user_utterance: str = "",
        simulate_user: bool = False,
        simulate_user_intent: str = "",
    ) -> ConversationTurn:
        """
        Yields a single turn in the conversation flow.

        This method take a user input when user choose to inject an utterance or generates the next system utterance based on the current conversation history and defined discourse policies.
        It handles updating the conversation history, managing expert lists, and interacting with the knowledge base.
        Additionally, it logs each stage of the conversation for monitoring and debugging purposes.

        Args:
            user_utterance (str, optional): The input provided by the user. If provided, this utterance is added directly to the conversation history and returns with no further action.
            simulate_user (bool, optional): This is designed for automatic experiments using a LLM agent to simulate user actions. Flag indicating whether to simulate user behavior. When set to `True`, the system will generate user intents based on predefined simulation logic. Defaults to `False`.
            simulate_user_intent (str, optional): This is designed for automatic experiments using a LLM agent to simulate user actions. Specifies the intent to simulate for the user. This is used when `simulate_user` is `True` to guide the simulated user's responses,

        Returns:
            ConversationTurn: An object representing the latest turn in the conversation.

        Workflow:
            1. User Utterance Handling
                - If `user_utterance` is provided, it is appended to the `conversation_history`

            2. System Utterance Generation
                - If no `user_utterance` is provided, the method proceeds to generate the next system utterance.
                - Determines the next turn policy by consulting the `discourse_manager` with the current conversation history.
                - Generates a new utterance using the agent defined in the turn policy, leveraging the `knowledge_base` and `conversation_history`.
                - If the turn policy indicates that the experts list should be updated, it updates the expert list based on the latest utterances.

            4. Knowledge Base Update
                - Inserts the new turn into the `knowledge_base`, optionally allowing the creation of new nodes or inserting under the root based on the `rag_only_baseline_mode` flag.
                - If the turn policy specifies, it reorganizes the `knowledge_base` to maintain optimal structure and relevance.
        """
        last_conv_turn = self.conversation_history[-1]
        cur_turn_name = f"conv turn: {len(self.conversation_history) + 1}"
        with self.logging_wrapper.log_pipeline_stage(
            pipeline_stage=f"{cur_turn_name} stage"
        ):
            conv_turn = None
            if user_utterance:
                self.discourse_manager.next_turn_moderator_override = False
                conv_turn = ConversationTurn(
                    role="Guest",
                    raw_utterance=user_utterance,
                    utterance_type="Original Question",
                )
                self.conversation_history.append(conv_turn)
            else:
                with self.logging_wrapper.log_event(
                    f"{cur_turn_name}: get turn policy"
                ):
                    if self.callback_handler is not None:
                        self.callback_handler.on_turn_policy_planning_start()
                    turn_policy = self.discourse_manager.get_next_turn_policy(
                        conversation_history=self.conversation_history,
                        simulate_user=simulate_user,
                        simulate_user_intent=simulate_user_intent,
                        dry_run=False,
                    )

                with self.logging_wrapper.log_event(
                    f"{cur_turn_name}: generate utterance"
                ):
                    conv_turn = turn_policy.agent.generate_utterance(
                        knowledge_base=self.knowledge_base,
                        conversation_history=self.conversation_history,
                    )

                if turn_policy.should_update_experts_list:
                    with self.logging_wrapper.log_event(
                        f"{cur_turn_name}: update experts list"
                    ):
                        self.discourse_manager._update_expert_list_from_utterance(
                            focus=last_conv_turn.raw_utterance,
                            background_info=conv_turn.raw_utterance,
                        )

                if conv_turn is not None:
                    self.conversation_history.append(conv_turn)
                    with self.logging_wrapper.log_event(
                        f"{cur_turn_name}: insert into knowledge base"
                    ):
                        if self.callback_handler is not None:
                            self.callback_handler.on_mindmap_insert_start()
                        self.knowledge_base.update_from_conv_turn(
                            conv_turn=conv_turn,
                            allow_create_new_node=True,
                            insert_under_root=self.runner_argument.rag_only_baseline_mode,
                        )
                        if self.callback_handler is not None:
                            self.callback_handler.on_mindmap_insert_end()
                if turn_policy.should_reorganize_knowledge_base:
                    with self.logging_wrapper.log_event(
                        f"{cur_turn_name}: reorganize knowledge base"
                    ):
                        if self.callback_handler is not None:
                            self.callback_handler.on_mindmap_reorg_start()
                        self.knowledge_base.reorganize()
        return conv_turn
