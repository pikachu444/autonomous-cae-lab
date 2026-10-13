# Windows and Qt visual design references

Checked 2026-10-14. These are short source-grounded summaries, not copied manuals.
Qt links are rolling documentation; the observed project runtime was PySide6
6.9.1. Confirm APIs against the actual runtime. Windows design principles can
inform Qt widgets; they do not require WinUI, QML or a product rewrite.

## VIS-TYPE Typography, Korean text, hierarchy

Source: [Typography in Windows](https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/typography).
Keywords: typography font Korean 글꼴 한글 글씨 위계 크기 hierarchy.

Source fact: Windows uses a consistent type system to make headings and body
text distinguishable and readable. It recommends consistent UI typography and
language-appropriate fonts. Its sizes are effective pixels, not raw display pixels.
Application inference: define a small title/body/secondary hierarchy, inspect
Korean fallback and chart labels together, and retain readable text in narrow
windows. Do not enlarge every label or shrink every control to make it fit.
Boundary: XAML type-ramp values are not Qt point sizes. No font files may be
copied into the product merely because Windows installed them.

## VIS-SPACE Alignment, spacing, information density

Source: [Content layout and spacing](https://learn.microsoft.com/en-us/windows/apps/design/basics/content-basics).
Keywords: spacing gutters alignment grid density 간격 여백 정렬 테두리 표.

Source fact: consistent spacing groups related controls; compact contexts can
use emphasized body text rather than a large heading. The guide illustrates
different spacing between controls and between larger content regions.
Application inference: choose a restrained spacing scale and use alignment and
space before adding another frame. Let engineering tables stay dense while
separating distinct tasks. Give the object name more space than a short status.
Boundary: the examples are design guidance, not a universal pixel mandate or a
reason to waste engineering work area on large dashboard cards.

## VIS-COLOR Surfaces, accent, readable state

Source: [Color in Windows](https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/color).
Keywords: palette neutral surface accent focus selection contrast 색상 배경 강조 선택.

Source fact: restrained color communicates hierarchy and interaction; sufficient
contrast and more than color alone are needed to communicate meaning.
Application inference: establish background/work-surface/text/border/selection
roles. Use accent for a meaningful primary action or selection, not every button.
Compare the same content in normal, selected, focused and disabled states.
Boundary: neither a dark theme nor rounded corners automatically makes an app
modern. Do not change data-series colors in ways that corrupt their meaning.

## WIN-COMMAND Primary versus secondary commands

Source: [Command bar](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/command-bar).
Keywords: command toolbar overflow primary action 버튼 도구 모음 발견성 동급.

Source fact: common actions should be easy to access; command importance affects
which commands remain visible as width shrinks. Secondary actions can use
overflow, but hiding all actions can confuse users. Labels should stay concise.
Application inference: expose the current task's main action near its object,
keep file commands consistent, and move rare configuration/diagnostics to menus.
Boundary: do not transplant WinUI controls, hide every button, or apply a mobile
command-count example as a desktop engineering requirement.

## QT-STYLE Styling real Qt Widgets

Source: [Qt Style Sheets Examples](https://doc.qt.io/qt-6/stylesheet-examples.html).
Keywords: QSS stylesheet QPalette QStyle QPushButton hover pressed focus 스타일 기본 회색.

Source fact: style sheets can target an application, a subtree, object names or
properties. Styling colors also requires care for text/selection contrast;
customized buttons need their interaction states to remain perceptible.
Application inference: reuse the existing style mechanism if present, otherwise
keep a small shared appearance module and scoped component treatment. Define
normal/hover/pressed/disabled/focus consistently; inspect menus and popups too.
Boundary: example colors and gradients demonstrate APIs, not recommended product
art direction. QSS is not browser CSS. Avoid broad selectors that damage embedded
editors, plots, accessibility or native FreeCAD/ParaView windows.

## QT-PANELS Docking and resizing

Sources: [QDockWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QDockWidget.html),
[QSplitter](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSplitter.html).
Keywords: dock splitter resize panel focus 도킹 패널 작은 창 편집.

Source fact: docks surround a central work area and may be movable, floatable
and closable. A splitter lets users resize adjacent widgets and preserve sizes.
Application inference: retain a clear central object. Open contextual editing
when needed rather than showing empty forms permanently; preserve user resizing.
Boundary: a dock API does not decide the right information architecture. Three
permanent columns can be worse than two on a small screen. Do not auto-rearrange
active edits or restore untrusted layout bytes.

## QT-ACCESS Scaling, keyboard and accessible state

Sources: [Qt accessibility](https://doc.qt.io/qt-6/accessible.html),
[High DPI](https://doc.qt.io/qt-6/highdpi.html).
Keywords: keyboard focus scaling DPI accessibility 한글 잘림 배율 키보드.

Source fact: Qt supports system fonts/palettes, keyboard navigation and scalable
layouts. Qt's higher-level geometry uses device-independent coordinates; image
buffers and lower-level graphics have their own pixel-density considerations.
Application inference: render relevant windows at ordinary and constrained
sizes and check actual scale factors; keep focus visible and captions readable.
Boundary: a 1x offscreen capture is not proof of real multi-monitor behavior.
Do not repair clipping by disabling high-DPI support or truncating critical units.
