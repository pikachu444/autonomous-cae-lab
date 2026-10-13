# Stanford OVAL STORM (MIT); two Wiki prompt signatures used by Co-STORM.
from . import prompting as dspy

class WritePageOutline(dspy.Signature):
    """Write an outline for a Wikipedia page.
    Here is the format of your writing:
    1. Use "#" Title" to indicate section title, "##" Title" to indicate subsection title, "###" Title" to indicate subsubsection title, and so on.
    2. Do not include other information.
    3. Do not include topic name itself in the outline.
    """

    topic = dspy.InputField(prefix="The topic you want to write: ", format=str)
    outline = dspy.OutputField(prefix="Write the Wikipedia page outline:\n", format=str)



class AskQuestionWithPersona(dspy.Signature):
    """You are an experienced Wikipedia writer and want to edit a specific page. Besides your identity as a Wikipedia writer, you have specific focus when researching the topic.
    Now, you are chatting with an expert to get information. Ask good questions to get more useful information.
    When you have no more question to ask, say "Thank you so much for your help!" to end the conversation.
    Please only ask a question at a time and don't ask what you have asked before. Your questions should be related to the topic you want to write.
    """

    topic = dspy.InputField(prefix="Topic you want to write: ", format=str)
    persona = dspy.InputField(
        prefix="Your persona besides being a Wikipedia writer: ", format=str
    )
    conv = dspy.InputField(prefix="Conversation history:\n", format=str)
    question = dspy.OutputField(format=str)

