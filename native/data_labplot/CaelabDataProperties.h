// SPDX-FileCopyrightText: 2026 Autonomous CAE Lab contributors
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <QAbstractButton>
#include <QApplication>
#include <QFrame>
#include <QGroupBox>
#include <QHash>
#include <QLabel>
#include <QLayout>
#include <QPointer>
#include <QScrollArea>
#include <QSizePolicy>
#include <QTabWidget>
#include <QVariant>
#include <QVBoxLayout>
#include <QWidget>

// Presentation of existing native editors only. No document, selection or Undo owner.
namespace CaelabDataProperties {

inline QString caption(const QString& original) {
    // Exact static UI captions from the pinned four dock forms and their widgets.
    // Free text, unknown captions, edit controls and combo item/data values stay intact.
    static const QHash<QString, QString> terms = [] {
        QHash<QString, QString> result;
        const char* pairs[][2] = {
            {"General", "일반"}, {"Title", "제목"}, {"Line", "선"}, {"Ticks", "눈금"},
            {"Labels", "눈금 글자"}, {"Grid", "격자"}, {"Symbol", "기호"},
            {"Values", "값 표시"}, {"Filling", "영역 채우기"}, {"Error Bars", "오차 막대"},
            {"Margins", "여백"}, {"Background", "배경"}, {"Layout", "배치"},
            {"Name", "이름"}, {"Comment", "설명"}, {"Orientation", "방향"},
            {"Position", "위치"}, {"Color", "색"}, {"Range", "범위"},
            {"Start", "시작"}, {"End", "끝"}, {"Scale", "축 척도"},
            {"Zero Offset", "영점 오프셋"}, {"Scaling Factor", "표시 배율"},
            {"Show scale and offset", "배율과 오프셋 표시"}, {"Plot Range", "그래프 범위"},
            {"Visible", "표시"}, {"Locked", "잠금"}, {"Legend", "범례"},
            {"Data", "자료"}, {"X-Data", "X 원열"}, {"Y-Data", "Y 원열"},
            {"Geometry", "크기와 위치"}, {"Size", "크기"}, {"Page", "용지"},
            {"Width", "너비"}, {"Height", "높이"}, {"Scale content", "내용 크기 조정"},
            {"Format", "서식"}, {"Font", "글꼴"}, {"Font Color", "글자 색"},
            {"Plot's Color", "곡선 색 사용"}, {"Columns", "열 수"}, {"Rows", "행 수"},
            {"Line+Symbol Width", "선과 기호 너비"}, {"Rotation", "회전"},
            {"Hor. align.", "가로 정렬"}, {"Ver. align.", "세로 정렬"},
            {"Logical coordinates", "자료 좌표 사용"}, {"Order", "순서"},
            {"Corner radius", "모서리 반지름"}, {"Border", "테두리"}, {"Spacing", "간격"},
            {"Top", "위"}, {"Bottom", "아래"}, {"Left", "왼쪽"}, {"Right", "오른쪽"},
            {"Vertical", "세로"}, {"Horizontal", "가로"},
            {"Arrow", "화살표"}, {"Type", "종류"}, {"Length", "길이"},
            {"Auto", "자동"}, {"Number", "개수"}, {"Direction", "방향"},
            {"Major Ticks", "주 눈금"}, {"Minor Ticks", "보조 눈금"},
            {"Major Grid", "주 격자"}, {"Minor Grid", "보조 격자"},
            {"1st Tick Value", "첫 눈금 값"}, {"1st Tick Offset", "첫 눈금 오프셋"},
            {"1st Tick at", "첫 눈금 위치"}, {"Increment", "증분"},
            {"Label Type", "글자 종류"}, {"Label Column", "글자 원열"},
            {"Position Column", "위치 원열"}, {"Precision", "정밀도"},
            {"Suffix", "접미사"}, {"Prefix", "접두사"}, {"Offset", "표시 간격"},
            {"Opacity", "불투명도"}, {"Text", "문자"}, {"Drop lines", "기준선 연결"},
            {"Connection", "연결"}, {"Interm. points", "보간점 수"},
            {"Ignore Gaps", "빈 구간 건너뛰기"}, {"Monoton incr. X", "X 증가 구간만 연결"},
            {"Enabled", "사용"}, {"Rug Plot", "축 위 자료 표시"},
            {"Load", "불러오기"}, {"Save", "저장"}, {"Manage", "관리"}, {"Theme", "테마"}
        };
        for (const auto& pair : pairs)
            result.insert(QString::fromUtf8(pair[0]), QString::fromUtf8(pair[1]));
        return result;
    }();
    QString key = original.trimmed();
    // KDE may add mnemonic markers to these same static captions. Normalize
    // only the lookup key; unknown text is returned exactly as supplied.
    key.remove(QLatin1Char('&'));
    const bool colon = key.endsWith(QLatin1Char(':'));
    if (colon) key.chop(1);
    const auto found = terms.constFind(key);
    if (found == terms.cend()) return original;
    QString translated = found.value();
    if (colon) translated += QLatin1Char(':');
    return translated;
}

inline void prepare(QWidget* nativeDock) {
    if (!nativeDock) return;
    QString title;
    if (nativeDock->inherits("AxisDock")) title = QString::fromUtf8("축 속성");
    else if (nativeDock->inherits("XYCurveDock")) title = QString::fromUtf8("곡선 속성");
    else if (nativeDock->inherits("CartesianPlotLegendDock")) title = QString::fromUtf8("범례 속성");
    else if (nativeDock->inherits("WorksheetDock")) title = QString::fromUtf8("그래프 작업면 속성");
    else return;

    nativeDock->setWindowTitle(title);
    for (auto* label : nativeDock->findChildren<QLabel*>()) label->setText(caption(label->text()));
    for (auto* button : nativeDock->findChildren<QAbstractButton*>()) button->setText(caption(button->text()));
    for (auto* group : nativeDock->findChildren<QGroupBox*>()) group->setTitle(caption(group->title()));
    for (auto* tabs : nativeDock->findChildren<QTabWidget*>()) {
        tabs->setUsesScrollButtons(true);
        for (int i = 0; i < tabs->count(); ++i) tabs->setTabText(i, caption(tabs->tabText(i)));
    }

    if (nativeDock->property("caelabPropertiesWrapped").toBool() || !nativeDock->layout()) return;
    QPointer<QWidget> focused = QApplication::focusWidget();
    const bool restoreFocus = focused && nativeDock->isAncestorOf(focused);
    auto* existing = nativeDock->layout();
    const int nativeMinimumWidth = nativeDock->minimumWidth();
    auto* body = new QWidget;
    body->setObjectName(QStringLiteral("caelabNativePropertiesBody"));
    // QWidget::setLayout reparents an existing layout from its old widget. Its
    // controls and all original native UI pointers/signal connections survive.
    body->setLayout(existing);
    existing->setSizeConstraint(QLayout::SetMinAndMaxSize);
    existing->activate();
    body->setMinimumWidth(qMax(320, qMax(nativeMinimumWidth, existing->minimumSize().width())));

    auto* scroll = new QScrollArea(nativeDock);
    scroll->setObjectName(QStringLiteral("caelabNativePropertiesScroll"));
    scroll->setAccessibleName(title);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setWidgetResizable(true);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll->setWidget(body);
    nativeDock->setMinimumSize(0, 0);
    auto* outer = new QVBoxLayout(nativeDock);
    outer->setObjectName(QStringLiteral("caelabNativePropertiesLayout"));
    outer->setSizeConstraint(QLayout::SetNoConstraint);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(0);
    outer->addWidget(scroll);
    nativeDock->setProperty("caelabPropertiesWrapped", true);
    scroll->show();
    if (restoreFocus && focused) {
        focused->setFocus(Qt::OtherFocusReason);
        scroll->ensureWidgetVisible(focused);
    }
}

} // namespace CaelabDataProperties
