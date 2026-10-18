// SPDX-FileCopyrightText: 2026 Autonomous CAE Lab contributors
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QScrollArea>
#include <QVariant>
#include <QVBoxLayout>
#include <QVector>
#include <cmath>

// An editable snapshot only. The bridge owns applying it and Project Undo.
class CaelabDataSettingsDialog : public QDialog {
public:
    CaelabDataSettingsDialog(const QJsonObject& draft, const QJsonArray& sourceColumns,
                            const QString& selectedChannel, QWidget* parent = nullptr)
        : QDialog(parent), m_draft(draft), m_sourceColumns(sourceColumns) {
        setWindowTitle(text("열과 단위"));
        setObjectName(QStringLiteral("coreDataSettings"));
        resize(800, 510);
        setMinimumSize(640, 420);
        auto* layout = new QVBoxLayout(this);
        auto* channelRow = new QHBoxLayout;
        m_channels = new QComboBox(this);
        m_channels->setObjectName(QStringLiteral("coreChannel"));
        m_channels->setMinimumContentsLength(10);
        m_channels->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
        m_newName = new QLineEdit(this);
        m_newName->setObjectName(QStringLiteral("coreNewChannel"));
        m_newName->setPlaceholderText(text("새 채널 이름"));
        auto* add = new QPushButton(text("채널 추가"), this);
        add->setObjectName(QStringLiteral("coreAddChannel"));
        add->setAutoDefault(false);
        auto* channelLabel = new QLabel(text("채널"), this);
        channelLabel->setBuddy(m_channels);
        channelRow->addWidget(channelLabel);
        channelRow->addWidget(m_channels, 2);
        channelRow->addWidget(m_newName, 1);
        channelRow->addWidget(add);
        layout->addLayout(channelRow);
        m_message = new QLabel(this);
        m_message->setWordWrap(true);
        m_message->hide();
        layout->addWidget(m_message);

        auto* scroll = new QScrollArea(this);
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        auto* body = new QWidget(scroll);
        auto* bodyLayout = new QVBoxLayout(body);
        bodyLayout->setContentsMargins(0, 0, 0, 0);
        auto* sources = new QHBoxLayout;
        auto* response = new QGroupBox(text("관측값"), body);
        auto* axis = new QGroupBox(text("가로축"), body);
        auto* responseGrid = new QGridLayout(response);
        auto* axisGrid = new QGridLayout(axis);
        m_valueColumn = sourceBox(QStringLiteral("coreValueColumn"), response);
        m_axisColumn = sourceBox(QStringLiteral("coreAxisColumn"), axis);
        labeled(responseGrid, 0, text("원자료 열"), m_valueColumn);
        labeled(responseGrid, 1, text("단위 이름"), field("unit", false, "coreValueUnit", response));
        numericPair(responseGrid, 2, false, response);
        labeled(axisGrid, 0, text("원자료 열"), m_axisColumn);
        labeled(axisGrid, 1, text("축 이름"), field("name", true, "coreAxisName", axis));
        labeled(axisGrid, 2, text("단위 이름"), field("unit", true, "coreAxisUnit", axis));
        numericPair(axisGrid, 3, true, axis);
        sources->addWidget(response, 1);
        sources->addWidget(axis, 1);
        bodyLayout->addLayout(sources);

        auto* physical = new QGroupBox(text("관측값의 물리적 의미"), body);
        auto* meaning = new QGridLayout(physical);
        auto* component = field("component", false, "coreValueComponent", physical);
        auto* location = field("location", false, "coreValueLocation", physical);
        auto* measure = field("measure", false, "coreValueMeasure", physical);
        auto* frame = field("frame", false, "coreValueFrame", physical);
        labeled(meaning, 0, text("성분"), component, 0, 1);
        labeled(meaning, 0, text("평가 위치"), location, 2, 1);
        labeled(meaning, 1, text("물리량 척도"), measure, 0, 1);
        labeled(meaning, 1, text("좌표계"), frame, 2, 1);
        component->setToolTip(text("원자료가 나타내는 성분을 그대로 지정합니다."));
        location->setToolTip(text("측정점·게이지 등 관측값의 평가 위치입니다."));
        measure->setToolTip(text("공학 변형률·Cauchy 응력 등 원자료의 물리적 척도입니다."));
        frame->setToolTip(text("이름을 바꾸는 것만으로 성분이나 좌표가 변환되지는 않습니다."));
        bodyLayout->addWidget(physical);
        bodyLayout->addStretch();
        scroll->setWidget(body);
        layout->addWidget(scroll, 1);

        auto* note = new QLabel(text("단위 이름을 바꿔도 수치는 변환되지 않습니다. 수치 변환은 배율·오프셋으로 따로 지정합니다.\n"
                                    "미완성 입력도 초안으로 보존되며, 자료 준비 전 유효성을 검사합니다."), this);
        note->setWordWrap(true);
        layout->addWidget(note);
        auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
        buttons->setObjectName(QStringLiteral("coreSettingsButtons"));
        buttons->button(QDialogButtonBox::Ok)->setText(text("편집 내용 사용"));
        buttons->button(QDialogButtonBox::Cancel)->setText(text("취소"));
        for (auto* button : buttons->buttons()) {
            if (auto* push = qobject_cast<QPushButton*>(button)) {
                push->setAutoDefault(false);
                push->setDefault(false);
            }
        }
        connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
        connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
        layout->addWidget(buttons);

        const auto columns = m_draft.value(QStringLiteral("mapping")).toObject().value(QStringLiteral("columns")).toObject();
        m_channels->addItems(columns.keys());
        const int chosen = m_channels->findText(selectedChannel);
        m_channels->setCurrentIndex(chosen >= 0 ? chosen : (m_channels->count() ? 0 : -1));
        m_channel = m_channels->currentText();
        loadCurrent();
        connect(m_channels, &QComboBox::currentIndexChanged, this, [this](int) {
            m_draft = editedDraft();
            m_channel = m_channels->currentText();
            loadCurrent();
        });
        connect(add, &QPushButton::clicked, this, [this] { addChannel(); });
        // Enter in the new-name field adds the channel, never accepts by surprise.
        connect(m_newName, &QLineEdit::returnPressed, this, [this] { addChannel(); });

        QVector<QWidget*> order{m_channels, m_newName, add, m_valueColumn};
        for (const auto& item : m_fields) if (!item.axis && item.key != QStringLiteral("component") &&
                item.key != QStringLiteral("location") && item.key != QStringLiteral("measure") && item.key != QStringLiteral("frame"))
            order.append(item.editor);
        order.append(m_axisColumn);
        for (const auto& item : m_fields) if (item.axis) order.append(item.editor);
        order << component << location << measure << frame << buttons->button(QDialogButtonBox::Ok)
              << buttons->button(QDialogButtonBox::Cancel);
        for (qsizetype i = 1; i < order.size(); ++i) setTabOrder(order[i - 1], order[i]);
        (m_channel.isEmpty() ? static_cast<QWidget*>(m_newName) : static_cast<QWidget*>(m_valueColumn))->setFocus();
    }

    QJsonObject editedDraft() const {
        auto result = m_draft;
        if (m_channel.isEmpty()) return result;
        auto mapping = result.value(QStringLiteral("mapping")).toObject();
        auto columns = mapping.value(QStringLiteral("columns")).toObject();
        auto response = columns.value(m_channel).toObject();
        auto axis = response.value(QStringLiteral("axis")).toObject();
        bool changed = false, axisChanged = false;
        auto putColumn = [&](QComboBox* box, const QString& initial, int initialIndex, QJsonObject& spec) {
            if (box->currentText() == initial && box->currentIndex() == initialIndex) return false;
            const auto value = box->currentIndex() >= 0 && box->currentText() == box->itemText(box->currentIndex())
                ? QJsonValue::fromVariant(box->currentData()) : QJsonValue(box->currentText());
            if (spec.value(QStringLiteral("column")) == value) return false;
            spec.insert(QStringLiteral("column"), value);
            return true;
        };
        changed = putColumn(m_valueColumn, m_valueText, m_valueIndex, response);
        axisChanged = putColumn(m_axisColumn, m_axisText, m_axisIndex, axis);
        for (const auto& item : m_fields) {
            if (item.editor->text() == item.initial) continue;
            auto& spec = item.axis ? axis : response;
            QJsonValue value(item.editor->text());
            if (item.numeric) {
                bool ok = false;
                const double number = item.editor->text().toDouble(&ok);
                if (ok && std::isfinite(number)) value = QJsonValue(number);
                if (!spec.contains(item.key) && value.isDouble() &&
                        value.toDouble() == (item.key == QStringLiteral("scale") ? 1.0 : 0.0)) continue;
            }
            if (spec.value(item.key) == value) continue;
            spec.insert(item.key, value);
            if (item.axis) axisChanged = true; else changed = true;
        }
        if (axisChanged) { response.insert(QStringLiteral("axis"), axis); changed = true; }
        if (changed) {
            columns.insert(m_channel, response);
            mapping.insert(QStringLiteral("columns"), columns);
            result.insert(QStringLiteral("mapping"), mapping);
        }
        return result;
    }

    QString selectedChannel() const { return m_channel; }

private:
    struct Field { QString key; bool axis; bool numeric; QLineEdit* editor; QString initial; };
    QJsonObject m_draft;
    QJsonArray m_sourceColumns;
    QString m_channel, m_valueText, m_axisText;
    int m_valueIndex{-1}, m_axisIndex{-1};
    QComboBox *m_channels, *m_valueColumn, *m_axisColumn;
    QLineEdit* m_newName;
    QLabel* m_message;
    QVector<Field> m_fields;

    static QString text(const char* value) { return QString::fromUtf8(value); }
    static QString shown(const QJsonValue& value) {
        if (value.isUndefined()) return {};
        if (value.isString()) return value.toString();
        QJsonArray wrapper; wrapper.append(value);
        const auto json = QJsonDocument(wrapper).toJson(QJsonDocument::Compact);
        return QString::fromUtf8(json.mid(1, json.size() - 2));
    }
    static void labeled(QGridLayout* grid, int row, const QString& title, QWidget* editor,
                        int column = 0, int span = 3) {
        auto* label = new QLabel(title, editor->parentWidget());
        label->setBuddy(editor);
        grid->addWidget(label, row, column);
        grid->addWidget(editor, row, column + 1, 1, span);
        grid->setColumnStretch(column + 1, 1);
    }
    QLineEdit* field(const char* key, bool axis, const char* name, QWidget* parent) {
        auto* edit = new QLineEdit(parent);
        edit->setObjectName(QString::fromLatin1(name));
        edit->setMinimumWidth(0);
        const auto fieldKey = QString::fromLatin1(key);
        const bool numeric = fieldKey == QStringLiteral("scale") || fieldKey == QStringLiteral("offset");
        m_fields.append({fieldKey, axis, numeric, edit, {}});
        return edit;
    }
    void numericPair(QGridLayout* grid, int row, bool axis, QWidget* parent) {
        auto* scale = field("scale", axis, axis ? "coreAxisScale" : "coreValueScale", parent);
        auto* offset = field("offset", axis, axis ? "coreAxisOffset" : "coreValueOffset", parent);
        labeled(grid, row, text("배율"), scale, 0, 1);
        labeled(grid, row, text("오프셋"), offset, 2, 1);
        scale->setToolTip(text("지정하지 않은 배율은 1입니다. 미완성 숫자는 초안으로 남습니다."));
        offset->setToolTip(text("지정하지 않은 오프셋은 0입니다. 단위 이름과 수치 변환은 별개입니다."));
    }
    QComboBox* sourceBox(const QString& name, QWidget* parent) {
        auto* box = new QComboBox(parent);
        box->setObjectName(name);
        box->setEditable(true);
        box->setInsertPolicy(QComboBox::NoInsert);
        box->setCompleter(nullptr);
        box->setMinimumContentsLength(8);
        box->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
        box->lineEdit()->setPlaceholderText(text("원자료 열 선택"));
        for (const auto entry : m_sourceColumns) {
            const auto descriptor = entry.toObject();
            const auto key = descriptor.value(QStringLiteral("key"));
            if (!key.isString() && !key.isDouble()) continue;
            auto name = descriptor.value(QStringLiteral("name")).toString();
            if (name.isEmpty()) name = shown(key);
            box->addItem(name, key.toVariant());
            box->setItemData(box->count() - 1, QString(text("원자료 열: ") + shown(key)), Qt::ToolTipRole);
        }
        return box;
    }
    static void loadColumn(QComboBox* box, const QJsonValue& value) {
        int index = -1;
        for (int i = 0; i < box->count(); ++i)
            if (QJsonValue::fromVariant(box->itemData(i)) == value) { index = i; break; }
        if (index < 0 && !value.isUndefined()) {
            box->addItem(text("현재 원열: ") + shown(value), value.toVariant());
            index = box->count() - 1;
        }
        box->setCurrentIndex(index);
        if (index < 0) box->setEditText({});
    }
    void loadCurrent() {
        const auto response = m_draft.value(QStringLiteral("mapping")).toObject()
            .value(QStringLiteral("columns")).toObject().value(m_channel).toObject();
        const auto axis = response.value(QStringLiteral("axis")).toObject();
        loadColumn(m_valueColumn, response.value(QStringLiteral("column")));
        loadColumn(m_axisColumn, axis.value(QStringLiteral("column")));
        m_valueText = m_valueColumn->currentText(); m_valueIndex = m_valueColumn->currentIndex();
        m_axisText = m_axisColumn->currentText(); m_axisIndex = m_axisColumn->currentIndex();
        m_valueColumn->setEnabled(!m_channel.isEmpty()); m_axisColumn->setEnabled(!m_channel.isEmpty());
        for (auto& item : m_fields) {
            const auto value = (item.axis ? axis : response).value(item.key);
            item.initial = value.isUndefined() && item.numeric
                ? (item.key == QStringLiteral("scale") ? QStringLiteral("1") : QStringLiteral("0")) : shown(value);
            item.editor->setText(item.initial);
            item.editor->setEnabled(!m_channel.isEmpty());
        }
    }
    void addChannel() {
        const auto name = m_newName->text().trimmed();
        auto edited = editedDraft();
        const auto mappingValue = edited.value(QStringLiteral("mapping"));
        const auto columnsValue = mappingValue.toObject().value(QStringLiteral("columns"));
        if ((!mappingValue.isUndefined() && !mappingValue.isObject()) ||
                (!columnsValue.isUndefined() && !columnsValue.isObject())) {
            m_message->setText(text("기존 열 대응 구조를 유지했습니다. 원 문서에서 구조를 확인하세요."));
            m_message->show();
            return;
        }
        auto mapping = edited.value(QStringLiteral("mapping")).toObject();
        auto columns = mapping.value(QStringLiteral("columns")).toObject();
        if (name.isEmpty() || columns.contains(name)) {
            m_message->setText(name.isEmpty() ? text("새 채널 이름을 입력하세요.") : text("같은 이름의 채널이 있습니다."));
            m_message->show(); m_newName->setFocus(); return;
        }
        columns.insert(name, QJsonObject{});
        mapping.insert(QStringLiteral("columns"), columns); edited.insert(QStringLiteral("mapping"), mapping);
        m_draft = edited;
        m_channels->blockSignals(true);
        m_channels->addItem(name); m_channels->setCurrentIndex(m_channels->count() - 1);
        m_channels->blockSignals(false);
        m_channel = name;
        m_newName->clear(); m_message->hide(); loadCurrent(); m_valueColumn->setFocus();
    }
};
