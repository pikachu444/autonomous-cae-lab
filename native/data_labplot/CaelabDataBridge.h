// SPDX-FileCopyrightText: 2026 Autonomous CAE Lab contributors
// SPDX-License-Identifier: GPL-2.0-or-later
// Bounded native Data integration using the fixed LabPlot work surface.
#pragma once
#include "MainWin.h"
#include "CaelabDataSettings.h"
#include "CaelabDataProperties.h"
#include "backend/core/Project.h"
#include "backend/core/column/Column.h"
#include "backend/lib/UndoStack.h"
#include "backend/spreadsheet/Spreadsheet.h"
#include "backend/worksheet/Worksheet.h"
#include "backend/worksheet/TextLabel.h"
#include "backend/worksheet/plots/cartesian/Axis.h"
#include "backend/worksheet/plots/cartesian/CartesianPlot.h"
#include "backend/worksheet/plots/cartesian/CartesianPlotLegend.h"
#include "backend/worksheet/plots/cartesian/XYCurve.h"
#include "frontend/spreadsheet/SpreadsheetView.h"
#include "frontend/core/ContentDockWidget.h"
#include "frontend/ProjectExplorer.h"
#include "frontend/worksheet/WorksheetView.h"
#include <DockManager.h>
#include <DockAreaWidget.h>
#include <DockSplitter.h>
#include <KActionCollection>
#include <QToolBar>
#include <QToolButton>
#include <QHeaderView>
#include <QScrollBar>
#include <QTreeView>
#include <QStackedWidget>
#include <QLabel>
#include <QProgressBar>
#include <QVBoxLayout>
#include <QStyle>
#include <QSignalBlocker>
#include <QEventLoop>
#include <QInputDialog>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMenuBar>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QLocalServer>
#include <QLocalSocket>
#include <QLockFile>
#include <QCryptographicHash>
#include <QScopedValueRollback>
#include <QScopeGuard>
#include <QPointer>
#include <QStatusBar>
#include <QApplication>
#include <QSaveFile>
#include <QCloseEvent>
#include <QUuid>
#include <QBuffer>
#include <QXmlStreamWriter>
#include <QXmlStreamReader>
#include <QFileDialog>
#include <QFileInfo>
#include <QDir>
#include <QStandardPaths>
#include <QProcess>
#include <QProcessEnvironment>
#include <QLibraryInfo>
#include <QElapsedTimer>
#include <QMessageBox>
#include <QDialogButtonBox>
#include <QPushButton>
#include <QTableView>
#include <QFormLayout>
#include <QComboBox>
#include <QLineEdit>
#include <QDoubleSpinBox>
#include <QGraphicsEllipseItem>
#include <QGraphicsRectItem>
#include <QGraphicsLineItem>
#include <QGraphicsSceneMouseEvent>
#include <QDynamicPropertyChangeEvent>
#include <QMouseEvent>
#include <QRubberBand>
#include <QSet>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <limits>
#include <functional>
#include <memory>

class CaelabDataBridge : public QObject {
    static QString text(const char* value) { return QString::fromUtf8(value); }
    MainWin* window;
    QNetworkAccessManager network;
    QPointer<Spreadsheet> sheet;
    QPointer<Worksheet> sourceWorksheet;
    QPointer<XYCurve> sourceCurve;
    QPointer<CartesianPlot> sourcePlot;
    QPointer<Spreadsheet> displayCache;
    QJsonArray rawColumns;
    QVector<int> displayOrder;
    QSet<int> selectedSources;
    QMetaObject::Connection selectionConnection, headerConnection, headerEditConnection, pointsConnection, xSourceConnection, ySourceConnection;
    QPointer<XYCurve> markerOwner;
    QList<QGraphicsItem*> markers;
    bool selecting{false}, refreshingView{false}, rangeSelection{false};
    QPoint rangeOrigin;
    QPointer<QRubberBand> rubberBand;
    QPointer<Project> connectedProject;
    QPointer<Project> boundProject;
    QMetaObject::Connection saveStateConnection;
    QJsonObject loadedBinding, confirmedReceipt, conflictCurrent;
    bool inputConflict{false};
    QString conflictJournal;
    QJsonObject savedAck, importedReference, pendingBinding;
    QByteArray pendingXml;
    QString pendingPath;
    bool serializing{false};
    QJsonObject baseline, draft;
    QString service, identifier, channel;
    QJsonArray rows;
    QJsonObject pendingApply;
    QMenu* menu;
    QAction *readAction, *excludeAction;
    QAction *applyAction, *saveAction, *prepareAction, *materialAction, *retryAction, *discussAction;
    QAction *settingsAction, *tableAction, *curveAction;
    QWidget* channelPane{nullptr};
    QLabel* channelSummary{nullptr};
    QComboBox* channelChoices{nullptr};
    bool updatingChannelPane{false}, sourceEditQueued{false}, analysisLayout{false}, narrowLayout{false}, compactToolsPrepared{false};
    CaelabDataSettingsDialog::Section nextMappingSection{CaelabDataSettingsDialog::Section::All}, sourceColumnSection{CaelabDataSettingsDialog::Section::Channel};
    QString prepareJob;
    QJsonObject lastPrepareJob;
    bool interactiveRequest{false};
    QList<QAction*> editActions;
    QList<QAction*> documentActions;
    QList<QPair<QPointer<QAction>, bool>> lockedActions;
    int loadEpoch{0};
    bool curveHasData{false};
    bool busy{false};
    bool workflowStarted{false};
    bool failNextViewWrite{false};
    // Same identity and bounded activation wire as Research result_return.py.
    struct ActivationLease {
        QString name, service, target, session;
        std::shared_ptr<QLockFile> lock;
        bool forwarded{false};
    };
    std::unique_ptr<ActivationLease> activation;
    QLocalServer* activationServer{nullptr};
    QSet<QLocalSocket*> activationConnections;
    bool activationReading{false};
    Project* activationProject{nullptr};
    QMetaObject::Connection activationDestroyedConnection;
    QString openingPath;
    QJsonObject openingBinding, openingDocument;
    std::unique_ptr<ActivationLease> openingLease;
    bool openingForwarded{false};
    bool pendingView() const { return !pendingXml.isEmpty() || !pendingBinding.isEmpty(); }

    QString activationService(const QString& serviceUrl = {}) const {
        const QUrl url(serviceUrl.isEmpty() ? service : serviceUrl);
        if (url.scheme() != text("http") || !QStringList{text("localhost"), text("127.0.0.1"), text("::1")}.contains(url.host()) ||
            !url.userInfo().isEmpty() || url.hasQuery() || url.hasFragment() || (!url.path().isEmpty() && url.path() != text("/")))
            throw std::runtime_error("Open the same local research service before activating Data.");
        return text("http://loopback:") + QString::number(url.port(80));
    }
    void releaseActivation() {
        QObject::disconnect(activationDestroyedConnection); activationProject = nullptr;
        const auto sockets = activationConnections;
        for (auto* socket : sockets) socket->abort();
        activationConnections.clear();
        if (activationServer) { activationServer->close(); activationServer->deleteLater(); activationServer = nullptr; }
        activation.reset();
    }
    std::unique_ptr<ActivationLease> prepareActivation(const QJsonObject& document, const QString& target = {}, const QString& serviceUrl = {}) {
        auto lease = std::make_unique<ActivationLease>();
        lease->service = activationService(serviceUrl); lease->target = document.value(text("id")).toString();
        lease->session = document.value(text("session_id")).toString();
        if (lease->target != (target.isEmpty() ? identifier : target) || document.value(text("kind")) != text("data") || lease->session.isEmpty())
            throw std::runtime_error("The exact Data document/session is unavailable.");
        const auto folder = QStandardPaths::writableLocation(QStandardPaths::GenericCacheLocation) + text("/autonomous-cae-lab/desktop");
        if (!QDir().mkpath(folder)) throw std::runtime_error("The Data activation directory is unavailable.");
        // Python Path.resolve() uses native separators on Windows. QJsonObject
        // serializes keys in lexical order, matching storage.canonical_hash.
        const auto userDirectory = QDir::toNativeSeparators(QDir(folder).canonicalPath());
        const QJsonObject key{{text("service"), lease->service}, {text("target"), lease->target}, {text("user_directory"), userDirectory}};
        const auto digest = QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(key).toJson(QJsonDocument::Compact), QCryptographicHash::Sha256).toHex());
        lease->name = text("caelab-research-") + digest;
        if (activation && activation->name == lease->name) { lease->lock = activation->lock; return lease; }
        lease->lock = std::make_shared<QLockFile>(folder + text("/") + digest + text(".lock"));
        lease->lock->setStaleLockTime(0);
        if (lease->lock->tryLock(0)) return lease;
        QLocalSocket socket; socket.setReadBufferSize(65537); socket.connectToServer(lease->name);
        if (!socket.waitForConnected(2500)) {
            const auto error = socket.error();
            // Python's absence probe briefly holds this same lock. Confirmed
            // pipe absence plus acquiring the lock is ownership, not a timeout
            // fallback or permission to steal a living editor's lease.
            if ((error == QLocalSocket::ServerNotFoundError || error == QLocalSocket::ConnectionRefusedError) && lease->lock->tryLock(2500)) return lease;
            throw std::runtime_error("The original Data editor is starting or unreachable. No replacement was opened.");
        }
        const QJsonObject message{{text("version"), 1}, {text("operation"), text("activate")}, {text("service"), lease->service},
            {text("target_id"), lease->target}, {text("session_id"), lease->session}};
        socket.write(QJsonDocument(message).toJson(QJsonDocument::Compact) + '\n'); socket.flush();
        QByteArray bytes; QElapsedTimer timer; timer.start();
        while (!bytes.contains('\n') && timer.elapsed() < 2500) {
            if (!socket.bytesAvailable()) socket.waitForReadyRead(qMax(1, 2500 - int(timer.elapsed())));
            bytes += socket.readAll();
            if (bytes.size() > 65536) throw std::runtime_error("Invalid Data activation receipt.");
            if (socket.state() == QLocalSocket::UnconnectedState && !socket.bytesAvailable()) break;
        }
        socket.abort();
        const auto receipt = QJsonDocument::fromJson(bytes).object();
        if (!bytes.contains('\n') || receipt.value(text("status")) != text("ACTIVATED") ||
            receipt.value(text("target_id")) != lease->target || receipt.value(text("session_id")) != lease->session)
            throw std::runtime_error("The original Data editor did not confirm this document/session. Its edits were preserved.");
        lease->forwarded = true;
        if (!activationServer && (!window->project() || (window->project()->fileName().isEmpty() && window->project()->childCount<AbstractAspect>() == 0)))
            QTimer::singleShot(0, window, &QWidget::close);
        window->statusBar()->showMessage(text("이미 열린 자료 창으로 이동했습니다."));
        return lease;
    }
    QJsonObject receiveActivation(const QJsonObject& message) {
        const QJsonObject identity{{text("target_id"), activation ? activation->target : QString()},
            {text("session_id"), activation ? activation->session : QString()}};
        auto rejected = identity; rejected.insert(text("status"), text("REJECTED"));
        if (!activation || message.keys() != QStringList{text("operation"), text("service"), text("session_id"), text("target_id"), text("version")} ||
            message.value(text("version")) != 1 || message.value(text("operation")) != text("activate") ||
            message.value(text("service")) != activation->service || message.value(text("target_id")) != activation->target ||
            message.value(text("session_id")) != activation->session || !connected() || identifier != activation->target ||
            baseline.value(text("session_id")) != activation->session || activationReading) return rejected;
        QScopedValueRollback<bool> reading(activationReading, true);
        try {
            const auto current = request(documentPath());
            if (current.value(text("id")) != activation->target || current.value(text("kind")) != text("data") ||
                current.value(text("session_id")) != activation->session) return rejected;
        } catch (...) { return rejected; }
        window->showNormal(); window->raise(); window->activateWindow();
        auto receipt = identity; receipt.insert(text("status"), text("ACTIVATED")); return receipt;
    }
    void commitActivation(std::unique_ptr<ActivationLease> lease) {
        if (activation && activation->name == lease->name) {
            activation->session = lease->session; return;
        }
        auto* server = new QLocalServer(this); server->setSocketOptions(QLocalServer::UserAccessOption);
        if (!server->listen(lease->name)) { server->deleteLater(); throw std::runtime_error("The Data activation endpoint could not be opened. The previous editor is preserved."); }
        QObject::connect(server, &QLocalServer::newConnection, this, [this, server] {
            while (server->hasPendingConnections()) {
                auto* socket = server->nextPendingConnection();
                if (activationConnections.size() >= 8) { socket->abort(); socket->deleteLater(); continue; }
                activationConnections.insert(socket); socket->setReadBufferSize(65537);
                auto bytes = std::make_shared<QByteArray>(); auto* timeout = new QTimer(socket);
                timeout->setSingleShot(true); timeout->setInterval(3000);
                QObject::connect(timeout, &QTimer::timeout, socket, &QLocalSocket::abort); timeout->start();
                auto read = [this, socket, bytes, timeout] {
                    *bytes += socket->readAll();
                    if (bytes->size() > 65536) { socket->abort(); return; }
                    if (!bytes->contains('\n')) return;
                    timeout->stop();
                    const auto receipt = receiveActivation(QJsonDocument::fromJson(*bytes).object());
                    socket->write(QJsonDocument(receipt).toJson(QJsonDocument::Compact) + '\n'); socket->flush(); socket->disconnectFromServer();
                };
                QObject::connect(socket, &QLocalSocket::readyRead, this, read);
                QObject::connect(socket, &QLocalSocket::disconnected, this, [this, socket] { activationConnections.remove(socket); socket->deleteLater(); });
                if (socket->bytesAvailable()) read();
            }
        });
        releaseActivation(); activation = std::move(lease); activationServer = server;
        activationProject = window->project();
        auto* owner = activationProject;
        activationDestroyedConnection = QObject::connect(owner, &QObject::destroyed, this, [this, owner] {
            if (activationProject == owner) releaseActivation();
        });
    }

    QJsonObject request(const QString& path, const QJsonObject* body = nullptr, const QString& serviceUrl = {}) {
        QNetworkRequest query{QUrl((serviceUrl.isEmpty() ? service : serviceUrl) + path)};
        query.setTransferTimeout(30000);
        if (body) {
            const auto overview = request(text("/api/overview"), nullptr, serviceUrl);
            query.setRawHeader(QByteArrayLiteral("X-CAE-Token"), overview.value(text("token")).toString().toUtf8());
            query.setHeader(QNetworkRequest::ContentTypeHeader, text("application/json"));
        }
        auto* reply = body ? network.post(query, QJsonDocument(*body).toJson(QJsonDocument::Compact)) : network.get(query);
        QEventLoop loop;
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        loop.exec(interactiveRequest ? QEventLoop::AllEvents : QEventLoop::ExcludeUserInputEvents);
        const auto bytes = reply->readAll();
        const auto error = reply->error();
        const auto errorMessage = reply->errorString();
        reply->deleteLater();
        const auto result = QJsonDocument::fromJson(bytes).object();
        if (error != QNetworkReply::NoError || result.isEmpty())
            throw std::runtime_error(result.value(text("error")).toString(errorMessage).toUtf8().constData());
        return result;
    }
    QString documentPath() const { return text("/api/workbench/documents/") + identifier; }
    void guarded(const std::function<void()>& action) {
        if (busy) return;
        busy = true; menu->setEnabled(false);
        try { action(); }
        catch (const std::exception& error) { window->statusBar()->showMessage(QString::fromUtf8(error.what())); }
        menu->setEnabled(true); busy = false; syncLocks();
    }
    void syncLocks() {
        if ((!pendingApply.isEmpty() || pendingView() || !prepareJob.isEmpty()) && lockedActions.isEmpty()) {
            for (auto* action : window->findChildren<QAction*>()) {
                if (action->parent() == menu || action == menu->menuAction()) continue;
                lockedActions.append({action, action->isEnabled()}); action->setEnabled(false);
                QObject::connect(action, &QAction::changed, this, [this, action] {
                    if ((!pendingApply.isEmpty() || pendingView() || !prepareJob.isEmpty()) && action->isEnabled()) action->setEnabled(false);
                });
            }
        } else if (pendingApply.isEmpty() && !pendingView() && prepareJob.isEmpty() && !lockedActions.isEmpty()) {
            const auto restore = lockedActions; lockedActions.clear();
            for (const auto& entry : restore) if (entry.first) entry.first->setEnabled(entry.second);
        }
        readAction->setEnabled(pendingApply.isEmpty() && !pendingView() && prepareJob.isEmpty());
        for (auto* action : documentActions) action->setEnabled(pendingApply.isEmpty() && !pendingView() && prepareJob.isEmpty());
        const bool ready = connected() && !inputConflict && pendingApply.isEmpty() && !pendingView() && prepareJob.isEmpty();
        for (auto* action : editActions) action->setEnabled(ready);
        excludeAction->setEnabled(ready);
        applyAction->setEnabled(ready && draft != baseline.value(text("draft")).toObject());
        saveAction->setEnabled(ready);
        prepareAction->setEnabled(ready && draft == baseline.value(text("draft")).toObject() && baseline.value(text("diagnostics")).toArray().isEmpty());
        materialAction->setEnabled(ready && !importedReference.value(text("job_id")).toString().isEmpty());
        discussAction->setEnabled(ready && draft == baseline.value(text("draft")).toObject());
        retryAction->setEnabled(!pendingApply.isEmpty() || pendingView() || !prepareJob.isEmpty());
    }
    bool eventFilter(QObject* watched, QEvent* event) override {
        if (watched == window && event->type() == QEvent::Resize && analysisLayout)
            QTimer::singleShot(0, this, [this] { arrangeAnalysisWorkspace(); });
        if (watched == sourceCurve && event->type() == QEvent::DynamicPropertyChange) {
            auto* change = static_cast<QDynamicPropertyChangeEvent*>(event);
            if (change->propertyName() == QByteArrayLiteral("caelab_hit") && displayCache && !selecting) {
                QSet<int> sources;
                for (const auto& item : sourceCurve->property("caelab_hit").toMap().value(text("indices")).toList()) {
                    const int index = item.toInt(); if (index >= 0 && index < displayCache->rowCount()) sources.insert(static_cast<int>(displayCache->column(0)->valueAt(index)));
                }
                selectSources(sources);
            }
        }
        if (rangeSelection && sourceWorksheet) {
            auto* view = dynamic_cast<WorksheetView*>(sourceWorksheet->view());
            if (view && watched == view->viewport()) {
                if (event->type() == QEvent::MouseButtonPress && static_cast<QMouseEvent*>(event)->button() == Qt::LeftButton) {
                    rangeOrigin = static_cast<QMouseEvent*>(event)->position().toPoint();
                    if (!rubberBand) rubberBand = new QRubberBand(QRubberBand::Rectangle, view->viewport());
                    rubberBand->setGeometry(QRect(rangeOrigin, QSize())); rubberBand->show(); return true;
                }
                if (event->type() == QEvent::MouseMove && rubberBand && rubberBand->isVisible()) {
                    rubberBand->setGeometry(QRect(rangeOrigin, static_cast<QMouseEvent*>(event)->position().toPoint()).normalized()); return true;
                }
                if (event->type() == QEvent::MouseButtonRelease && rubberBand && rubberBand->isVisible()) {
                    const auto area = rubberBand->geometry(); rubberBand->hide(); QSet<int> selected;
                    if (displayCache && sourcePlot && sourceCurve) for (int row = 0; row < displayCache->rowCount(); ++row) {
                        bool visible = false;
                        const auto point = sourcePlot->coordinateSystem(sourceCurve->coordinateSystemIndex())->mapLogicalToScene(QPointF(displayCache->column(1)->valueAt(row), displayCache->column(2)->valueAt(row)), visible);
                        if (visible && area.contains(view->mapFromScene(sourceCurve->graphicsItem()->mapToScene(point)))) selected.insert(static_cast<int>(displayCache->column(0)->valueAt(row)));
                    }
                    selectSources(selected); return true;
                }
            }
        }
        if (watched == window && event->type() == QEvent::Close && (!pendingApply.isEmpty() || pendingView() || !prepareJob.isEmpty())) {
            static_cast<QCloseEvent*>(event)->ignore();
            window->statusBar()->showMessage(text("진행 중인 자료 준비 상태 또는 저장을 먼저 확인하세요. 창을 닫아도 취소가 확정되지는 않습니다."));
            return true;
        }
        return QObject::eventFilter(watched, event);
    }
    class DraftChange : public QUndoCommand {
        QPointer<CaelabDataBridge> bridge;
        QJsonObject before, after;
        int epoch;
        QString beforeChannel, afterChannel;
    public:
        DraftChange(CaelabDataBridge* owner, const QJsonObject& value, const QString& valueChannel = {})
            : QUndoCommand(CaelabDataBridge::text("자료 편집")), bridge(owner), before(owner->draft), after(value), epoch(owner->loadEpoch), beforeChannel(owner->channel), afterChannel(valueChannel.isEmpty() ? owner->channel : valueChannel) {}
        void undo() override { if (bridge && bridge->connected() && bridge->loadEpoch == epoch && bridge->pendingApply.isEmpty() && !bridge->pendingView() && bridge->prepareJob.isEmpty()) { bridge->draft = before; bridge->channel = beforeChannel; bridge->refreshEngineeringView(); bridge->connectedProject->setChanged(true); bridge->syncLocks(); } }
        void redo() override { if (bridge && bridge->connected() && bridge->loadEpoch == epoch && bridge->pendingApply.isEmpty() && !bridge->pendingView() && bridge->prepareJob.isEmpty()) { bridge->draft = after; bridge->channel = afterChannel; bridge->refreshEngineeringView(); bridge->connectedProject->setChanged(true); bridge->syncLocks(); } }
    };
    void load(const QJsonObject& preparedDocument = {}, std::unique_ptr<ActivationLease> lease = {}) {
        if (!prepareJob.isEmpty()) throw std::runtime_error("진행 중인 자료 준비 상태를 먼저 확인하세요. 원 입력은 유지됩니다.");
        if (!pendingApply.isEmpty() || pendingView()) throw std::runtime_error("Complete the pending command or exact view save before reading another Core input.");
        if (requiresCoreSave() && (inputConflict || draft != baseline.value(text("draft")).toObject()) &&
            QMessageBox::question(window, text("Unapplied Data edits"), text("Discard local Data edits and read Core again?"), QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Discard) return;
        if (!connected() && !loadedBinding.isEmpty()) {
            if (service.isEmpty()) service = loadedBinding.value(text("service_url")).toString();
            identifier = loadedBinding.value(text("document")).toObject().value(text("id")).toString();
        }
        if (service.isEmpty() || identifier.isEmpty())
            throw std::runtime_error("Set CAELAB_SERVICE_URL and CAELAB_DATA_DOCUMENT_ID for the bounded donor trial.");
        const auto document = preparedDocument.isEmpty() ? request(documentPath()) : preparedDocument;
        if (!lease) lease = prepareActivation(document);
        if (lease->forwarded) return;
        auto* explorerTree = window->m_projectExplorer->findChild<QTreeView*>();
        const bool animated = explorerTree && explorerTree->isAnimated();
        // Expansion animations cache the old names/columns while the source
        // workbook is being assembled. User-initiated expansion stays animated.
        if (explorerTree) explorerTree->setAnimated(false);
        const auto restoreAnimation = qScopeGuard([explorerTree, animated] {
            if (explorerTree) explorerTree->setAnimated(animated);
        });
        baseline = document; draft = baseline.value(text("draft")).toObject(); ++loadEpoch;
        importedReference = {}; savedAck = {};
        inputConflict = false;
        attachProject();
        const bool newNativeDocument = connectedProject->fileName().isEmpty() && connectedProject->childCount<AbstractAspect>() == 0;
        if (newNativeDocument) connectedProject->setName(baseline.value(text("title")).toString(text("자료")));
        auto mapping = draft.value(text("mapping")).toObject();
        const auto channels = mapping.value(text("columns")).toObject();
        channel = channels.contains(text("stress")) ? text("stress") : channels.keys().value(0);
        QJsonArray columns;
        QJsonObject sourceIdentity;
        rows = {};
        int start = 0;
        do {
            const auto page = request(documentPath() + text("/source-table?start=") + QString::number(start) + text("&count=4096"));
            for (const auto* key : {"document_id", "session_id", "generation", "input_revision"}) {
                const auto name = text(key);
                const auto expected = baseline.value(name == text("document_id") ? text("id") : name);
                if (page.value(text(key)) != expected) throw std::runtime_error("Core input changed during source paging.");
            }
            const auto incoming = page.value(text("columns")).toArray();
            const QJsonObject identity{{text("data_id"), page.value(text("data_id"))},
                {text("sha256"), page.value(text("sha256"))}, {text("source_row_kind"), page.value(text("source_row_kind"))},
                {text("input_sha256"), page.value(text("input_sha256"))}};
            if (sourceIdentity.isEmpty()) sourceIdentity = identity;
            else if (sourceIdentity != identity || incoming.size() != columns.size())
                throw std::runtime_error("Source identity changed during paging; no mixed table was published.");
            if (columns.isEmpty()) columns = incoming;
            else for (int c = 0; c < columns.size(); ++c) {
                auto column = columns[c].toObject(); auto values = column.value(text("values")).toArray();
                for (const auto value : incoming[c].toObject().value(text("values")).toArray()) values.append(value);
                column.insert(text("values"), values); columns[c] = column;
            }
            for (const auto row : page.value(text("source_rows")).toArray()) rows.append(row);
            start += page.value(text("count")).toInt();
            if (start >= page.value(text("total_rows")).toInt()) break;
            if (page.value(text("count")).toInt() == 0) throw std::runtime_error("Source paging made no progress.");
        } while (true);
        rawColumns = columns; displayOrder.clear(); selectedSources.clear(); displayCache.clear(); sourceCurve.clear(); sourcePlot.clear();
        for (int index = 0; index < rows.size(); ++index) displayOrder.append(index);
        auto* created = new Spreadsheet(text("원자료"));
        created->setColumnCount(columns.size() + 1); created->setRowCount(rows.size());
        QVector<double> sourceRows;
        for (const auto row : rows) sourceRows.append(row.toDouble());
        created->column(0)->setName(text("원행")); created->column(0)->setValues(sourceRows);
        for (int c = 0; c < columns.size(); ++c) {
            const auto descriptor = columns[c].toObject(); QVector<double> values;
            for (const auto value : descriptor.value(text("values")).toArray()) {
                bool valid = false;
                const double number = value.isDouble() ? value.toDouble() : value.toString().toDouble(&valid);
                values.append(value.isDouble() || valid ? number : std::numeric_limits<double>::quiet_NaN());
            }
            created->column(c + 1)->setName(descriptor.value(text("name")).toString());
            created->column(c + 1)->setValues(values);
        }
        created->setReadOnly(true); window->addAspectToProject(created); sheet = created;
        const auto spec = channels.value(channel).toObject();
        const auto axisKey = spec.value(text("axis")).toObject().value(text("column"));
        int x = -1, y = -1;
        for (int c = 0; c < columns.size(); ++c) {
            const auto key = columns[c].toObject().value(text("key"));
            if (key == axisKey) x = c + 1;
            if (key == spec.value(text("column"))) y = c + 1;
        }
        if (!columns.isEmpty()) {
            auto* worksheet = new Worksheet(text("응답 곡선")); sourceWorksheet = worksheet;
            auto* plot = new CartesianPlot(text("원자료 응답")); sourcePlot = plot;
            worksheet->addChild(plot); plot->setType(CartesianPlot::Type::TwoAxes);
            worksheet->setPageRect(QRectF(0, 0, 2100, 1400));
            worksheet->setUseViewSize(true);
            worksheet->setLayout(Worksheet::Layout::VerticalLayout);
            worksheet->setProperty("caelab_data_analysis", true);
            plot->setRect(QRectF(150, 100, 1800, 1120));
            plot->setHorizontalPadding(190); plot->setVerticalPadding(150);
            plot->title()->setText(TextLabel::TextWrapper(text("<p align=\"center\" style=\"font-size:8pt\">원자료 응답 (배율·오프셋·교정 적용 전)<br/><span style=\"font-size:7pt\"><span style=\"color:#0071bc\">○ 선택</span>　<span style=\"color:#aa3228\">× 계산 제외</span>　<span style=\"color:#b57900\">□ 품질 확인 필요</span></span></p>"), TextLabel::Mode::Text, true));
            const auto axisSpec = spec.value(text("axis")).toObject();
            const QString xLabel = axisSpec.value(text("name")).toString() + text(" (") + rawUnitLabel(axisSpec) + text(")");
            const QString yLabel = channel + text(" (") + rawUnitLabel(spec) + text(")");
            for (auto* axis : plot->children<Axis>()) {
                axis->title()->setText(TextLabel::TextWrapper(axis->orientation() == WorksheetElement::Orientation::Horizontal ? xLabel : yLabel));
                auto font = axis->labelsFont(); font.setPointSizeF(Worksheet::convertToSceneUnits(9, Worksheet::Unit::Point)); axis->setLabelsFont(font);
                font.setPointSizeF(8); axis->title()->setFont(font);
                axis->setMajorTicksAutoNumber(false); axis->setMajorTicksNumber(5);
                axis->setMinorTicksDirection(Axis::noTicks);
                if (axis->orientation() == WorksheetElement::Orientation::Vertical) axis->setTitleOffsetX(-65);
            }
            auto* curve = new XYCurve(channel); sourceCurve = curve; plot->addChild(curve);
            if (x >= 0) curve->setXColumn(created->column(x)); if (y >= 0) curve->setYColumn(created->column(y));
            window->addAspectToProject(worksheet);
            worksheet->setZoomFit(Worksheet::ZoomFit::Fit);
            curveHasData = curve->hasData();
        }
        attachInteraction(); writeSourceOrder(); refreshEngineeringView();
        analysisLayout = true; arrangeAnalysisWorkspace(true);
        foldNativeTools();
        window->m_projectExplorer->setDataWorkspaceMode(true);
        QTimer::singleShot(0, this, [this] { refreshExplorerNames(); });
        window->m_propertiesDock->dockAreaWidget()->setMinimumWidth(220);
        if (newNativeDocument) QTimer::singleShot(0, this, [this] {
            if (!connected()) return;
            auto* area = window->m_projectExplorerDock->dockAreaWidget(); auto* splitter = area->parentSplitter();
            if (!splitter) return;
            auto sizes = splitter->sizes(); const int explorer = splitter->indexOf(area); int content = -1;
            for (int index = 0; index < sizes.size(); ++index) if (index != explorer && (content < 0 || sizes[index] > sizes[content])) content = index;
            if (explorer >= 0 && content >= 0) { sizes[content] += sizes[explorer] - 170; sizes[explorer] = 170; window->m_dockManagerMain->setSplitterSizes(area, sizes); }
            auto* properties = window->m_propertiesDock->dockAreaWidget(); auto* propertySplitter = properties->parentSplitter();
            if (!propertySplitter) return;
            auto widths = propertySplitter->sizes(); const int propertyIndex = propertySplitter->indexOf(properties); int center = -1;
            for (int index = 0; index < widths.size(); ++index) if (index != propertyIndex && (center < 0 || widths[index] > widths[center])) center = index;
            if (propertyIndex >= 0 && center >= 0) { widths[center] += widths[propertyIndex] - 220; widths[propertyIndex] = 220; window->m_dockManagerMain->setSplitterSizes(properties, widths); }
        });
        showChannelPane();
        const auto runs = baseline.value(text("runs")).toArray();
        for (int index = runs.size() - 1; index >= 0; --index) {
            const auto run = runs[index].toObject();
            if (!run.value(text("is_current_input")).toBool()) continue;
            const auto jobId = run.value(text("job_id")).toString();
            const auto state = request(text("/api/workbench/jobs/") + jobId).value(text("state")).toString();
            if (state == text("SUCCEEDED") && importedReference.isEmpty()) importedReference = QJsonObject{{text("document_id"), identifier}, {text("job_id"), jobId}};
            else if (state == text("QUEUED") || state == text("RUNNING") || state == text("CANCEL_REQUESTED") || state == text("CLEANUP_PENDING")) { prepareJob = jobId; break; }
        }
        syncLocks();
        window->statusBar()->showMessage(text("원자료를 읽었습니다. 원행과 채널을 선택하고 편집한 뒤 변경 적용을 누르세요."));
        commitActivation(std::move(lease));
    }
    void exclude() {
        if (inputConflict) throw std::runtime_error("The local input is in conflict. Its recovery file is preserved; explicitly reload before editing.");
        if (!pendingApply.isEmpty() || pendingView()) throw std::runtime_error("Confirm the pending command and exact view save before editing again.");
        if (!sheet || !window->project()) return;
        auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
        if (!view) return;
        auto mapping = draft.value(text("mapping")).toObject(); auto channels = mapping.value(text("columns")).toObject();
        auto spec = channels.value(channel).toObject(); auto selection = spec.value(text("row_selection")).toObject();
        auto excluded = selection.value(text("exclude_rows")).toArray();
        for (int row = 0; row < sheet->rowCount(); ++row) {
            if (!view->isRowSelected(row, false)) continue;
            const int source = static_cast<int>(sheet->column(0)->valueAt(row));
            if (!excluded.contains(source)) excluded.append(source);
        }
        selection.insert(text("exclude_rows"), excluded); spec.insert(text("row_selection"), selection);
        channels.insert(channel, spec); mapping.insert(text("columns"), channels);
        auto edited = draft; edited.insert(text("mapping"), mapping);
        window->project()->undoStack()->push(new DraftChange(this, edited));
        window->statusBar()->showMessage(text("Local calculation exclusions changed. Core is unchanged until Apply."));
    }
    QJsonObject channelSpec() const { return draft.value(text("mapping")).toObject().value(text("columns")).toObject().value(channel).toObject(); }
    static QString rawUnitLabel(const QJsonObject& spec) {
        // The reader's unit describes transformed values. Only calibration
        // declares a separate raw unit; affine coefficients cannot prove it.
        if (spec.contains(text("calibration"))) {
            const auto unit = spec.value(text("calibration")).toObject().value(text("input_unit")).toString();
            return unit.isEmpty() ? text("원단위 미지정") : unit;
        }
        const auto scale = spec.value(text("scale")), offset = spec.value(text("offset"));
        const bool identity = (scale.isUndefined() || (scale.isDouble() && scale.toDouble() == 1))
            && (offset.isUndefined() || (offset.isDouble() && offset.toDouble() == 0));
        const auto unit = spec.value(text("unit")).toString();
        return identity && !unit.isEmpty() ? unit : text("원단위 미지정");
    }
    bool rowUsed(int source) const {
        const auto selection = channelSpec().value(text("row_selection")).toObject();
        auto within = [source](const QJsonArray& ranges) { for (const auto value : ranges) { const auto range = value.toArray(); if (range.size() == 2 && range[0].toInt() <= source && source <= range[1].toInt()) return true; } return false; };
        return (!selection.contains(text("include_ranges")) || within(selection.value(text("include_ranges")).toArray())) && !selection.value(text("exclude_rows")).toArray().contains(source) && !within(selection.value(text("exclude_ranges")).toArray());
    }
    double rawNumber(int column, int row) const {
        if (column < 0 || column >= rawColumns.size()) return std::numeric_limits<double>::quiet_NaN();
        const auto values = rawColumns[column].toObject().value(text("values")).toArray();
        if (row < 0 || row >= values.size()) return std::numeric_limits<double>::quiet_NaN();
        const auto value = values.at(row);
        if (value.isDouble()) return value.toDouble();
        bool valid = false; const auto number = value.toString().toDouble(&valid);
        return valid ? number : std::numeric_limits<double>::quiet_NaN();
    }
    // Presentation is derived from the current mapping, never from a column's
    // spelling. Keep raw keys/values and all alternate mappings intact.
    void refreshSourceHeaders() {
        if (!sheet) return;
        const auto columns = draft.value(text("mapping")).toObject().value(text("columns")).toObject();
        const auto active = columns.value(channel).toObject(), axis = active.value(text("axis")).toObject();
        auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
        auto* table = view ? view->findChild<QTableView*>() : nullptr;
        for (int index = 0; index < sheet->columnCount(); ++index) {
            auto* column = sheet->column(index); QString name, detail, tooltip;
            if (index == 0) { name = text("원행"); detail = text("원자료 행"); tooltip = text("정렬·숨김 후에도 유지되는 원자료 행 번호"); }
            else if (index > rawColumns.size()) {
                name = index == rawColumns.size() + 1 ? text("계산") : text("품질");
                detail = index == rawColumns.size() + 1 ? text("사용 여부") : text("확인 표시"); tooltip = name + text(" — 선택 채널에만 적용");
            } else {
                const auto descriptor = rawColumns[index - 1].toObject(); const auto key = descriptor.value(text("key"));
                const auto original = descriptor.value(text("name")).toString();
                QStringList bindings, names, units;
                auto binding = [&](const QString& label, const QJsonObject& spec, const QString& role) {
                    if (spec.value(text("column")) != key) return;
                    const auto unit = rawUnitLabel(spec), output = spec.value(text("unit")).toString();
                    if (!label.isEmpty() && !names.contains(label)) names.append(label);
                    if (!unit.isEmpty() && !units.contains(unit)) units.append(unit);
                    bindings.append(label + text(" — ") + role + text("\n  원값 단위: ") + unit
                        + text("\n  준비 후 채널 단위: ") + (output.isEmpty() ? text("미지정") : output));
                };
                for (auto it = columns.begin(); it != columns.end(); ++it) {
                    binding(it.key(), it.value().toObject(), text("응답"));
                    const auto mappedAxis = it.value().toObject().value(text("axis")).toObject();
                    binding(mappedAxis.value(text("name")).toString(), mappedAxis, it.key() + text(" 가로축"));
                }
                const bool isY = active.value(text("column")) == key, isX = axis.value(text("column")) == key;
                // Generic reader labels have no engineering meaning. Show the
                // explicitly declared active channel/axis without guessing units.
                name = original;
                if (original.isEmpty() || original == text("열 ") + QString::number(index)) {
                    if (isY) name = channel;
                    else if (isX && !axis.value(text("name")).toString().isEmpty()) name = axis.value(text("name")).toString();
                    else if (!names.isEmpty()) name = names.join(text(" / "));
                    else name = text("열 ") + QString::number(index);
                }
                detail = units.isEmpty() ? text("원단위 미지정") : units.join(text(" / "));
                if (isX || isY) detail += isX && isY ? text(" · X/Y") : isX ? text(" · X") : text(" · Y");
                if (isY && name != channel) detail += text(" · ") + channel;
                else if (isX && name != axis.value(text("name")).toString()) detail += text(" · ") + axis.value(text("name")).toString();
                tooltip = text("원열: ") + (original.isEmpty() ? text("이름 없음") : original) + text("\n열 위치: ") + QString::number(index)
                    + text("\n원열 키: ") + key.toVariant().toString() + text("\n")
                    + (bindings.isEmpty() ? text("연결된 채널 없음 — 단위·물리량을 추정하지 않습니다.") : bindings.join(text("\n")))
                    + text("\n원자료 값 — 배율·오프셋·교정 적용 전");
            }
            column->setProperty("caelab_source_header", QString(name + text("\n") + detail));
            column->setProperty("caelab_source_tooltip", tooltip);
            column->setName(name);
            if (table && !column->property("caelab_source_width_set").toBool()) {
                const int width = index == 0 ? 76 : index > rawColumns.size() ? 88 : qBound(96, qMax(table->fontMetrics().horizontalAdvance(name), table->fontMetrics().horizontalAdvance(detail)) + 22, 176);
                table->setColumnWidth(index, width); column->setProperty("caelab_source_width_set", true);
            }
        }
        if (table) {
            // Native header settings still apply to independent spreadsheets.
            table->model()->headerDataChanged(Qt::Horizontal, 0, sheet->columnCount() - 1);
            table->horizontalHeader()->setMinimumHeight(44);
            table->horizontalHeader()->setTextElideMode(Qt::ElideRight);
            auto* header = table->horizontalHeader();
            header->setSectionsMovable(true);
            if (!table->property("caelab_source_order_set").toBool()) {
                // Initial view only: put the declared X/Y beside the row id.
                // Logical columns and later user dragging remain unchanged.
                int position = 1;
                for (const auto key : {axis.value(text("column")), active.value(text("column"))}) {
                    for (int index = 0; index < rawColumns.size(); ++index) {
                        if (rawColumns[index].toObject().value(text("key")) != key) continue;
                        const int visual = header->visualIndex(index + 1);
                        if (visual >= position) header->moveSection(visual, position++);
                        break;
                    }
                }
                table->setProperty("caelab_source_order_set", true);
            }
            if (table->property("caelab_source_channel").toString() != channel) {
                table->setProperty("caelab_source_channel", channel);
                table->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
                for (int index = 0; index < rawColumns.size(); ++index) if (rawColumns[index].toObject().value(text("key")) == active.value(text("column"))) {
                    const int left = header->sectionViewportPosition(index + 1), width = header->sectionSize(index + 1);
                    if (left < 0 || left + width > table->viewport()->width())
                        table->horizontalScrollBar()->setValue(table->horizontalScrollBar()->value() + left + width / 2 - table->viewport()->width() / 2);
                    break;
                }
            }
        }
    }
    void arrangeAnalysisWorkspace(bool force = false) {
        if (!connected() || !sheet || !sourceWorksheet || !analysisLayout) return;
        const bool narrow = window->width() < 1180;
        if (!force && narrow == narrowLayout) return;
        narrowLayout = narrow;
        const auto chosenRows = selectedSources;
        QPointer<AbstractAspect> chosenAspect = window->m_projectExplorer->currentAspect();
        const bool explicitNativeAspect = chosenAspect && chosenAspect != sheet && chosenAspect != sourceWorksheet && chosenAspect->parentAspect() != sheet;
        auto* tableDock = sheet->dockWidget(); auto* curveDock = sourceWorksheet->dockWidget();
        if (!tableDock || !curveDock || !tableDock->dockAreaWidget()) return;
        if (narrow) {
            window->m_dockManagerContent->addDockWidgetTabToArea(curveDock, tableDock->dockAreaWidget());
            tableDock->setAsCurrentTab();
        } else {
            window->m_dockManagerContent->addDockWidget(ads::RightDockWidgetArea, curveDock, tableDock->dockAreaWidget());
            window->m_dockManagerContent->setSplitterSizes(tableDock->dockAreaWidget(), {600, 400});
            QTimer::singleShot(0, this, [this] { if (connected() && sheet && analysisLayout && !narrowLayout) window->m_dockManagerContent->setSplitterSizes(sheet->dockWidget()->dockAreaWidget(), {600, 400}); });
            tableDock->setAsCurrentTab(); curveDock->setAsCurrentTab();
        }
        selectSources(chosenRows);
        // QADS activation during our own responsive redocking must not replace
        // an explicitly selected axis, curve, legend or independent worksheet.
        if (explicitNativeAspect && chosenAspect) {
            for (auto* owner = chosenAspect.data(); owner; owner = owner->parentAspect()) {
                if (auto* part = dynamic_cast<AbstractPart*>(owner)) { part->dockWidget()->setAsCurrentTab(); break; }
            }
            window->m_projectExplorer->setCurrentAspect(chosenAspect);
        }
    }
    void foldNativeTools() {
        if (compactToolsPrepared) return;
        compactToolsPrepared = true;
        QMenu* viewMenu = nullptr;
        for (auto* action : window->menuBar()->actions()) {
            auto label = action->text(); label.remove(QLatin1Char('&'));
            if (label == text("보기")) viewMenu = action->menu();
        }
        auto* nativeMenu = viewMenu ? viewMenu->addMenu(text("기본 도구 모음")) : nullptr;
        for (auto* toolbar : window->findChildren<QToolBar*>()) {
            const auto name = toolbar->objectName();
            if (name != text("mainToolBar") && name != text("main_toolbar") && name != text("worksheet_toolbar") && name != text("cartesian_plot_toolbar")) continue;
            toolbar->setProperty("caelab_default_collapsed", true); toolbar->hide();
            auto* toggle = toolbar->toggleViewAction();
            if (nativeMenu) nativeMenu->addAction(toggle);
            QObject::connect(toggle, &QAction::triggered, this, [toolbar](bool visible) {
                // Explicitly restoring an original toolbar wins over the default.
                if (visible) toolbar->setProperty("caelab_default_collapsed", false);
            });
        }
    }
    void refreshExplorerNames() {
        if (!connected()) return;
        auto* explorer = window->m_projectExplorer;
        auto* tree = explorer->findChild<QTreeView*>(text("caelabDataExplorerTree"));
        if (!tree) return;
        // Reapply the existing name-first policy after source renaming and dock
        // activation. Rebuild visual item geometry without resetting selection.
        QMetaObject::invokeMethod(explorer, "resizeHeader", Qt::DirectConnection);
        tree->doItemsLayout(); tree->viewport()->update();
    }
    void showChannelPane() {
        if (!connected() || !channelPane) return;
        updatingChannelPane = true; channelChoices->clear();
        const auto columns = draft.value(text("mapping")).toObject().value(text("columns")).toObject();
        for (auto it = columns.begin(); it != columns.end(); ++it) {
            const auto spec = it.value().toObject();
            channelChoices->addItem(it.key() + text(" (") + spec.value(text("unit")).toString() + text(")"), it.key());
        }
        channelChoices->setCurrentIndex(channelChoices->findData(channel)); updatingChannelPane = false;
        channelChoices->setToolTip(channelChoices->currentText());
        const auto spec = columns.value(channel).toObject();
        QString rawName;
        for (const auto descriptor : rawColumns) if (descriptor.toObject().value(text("key")) == spec.value(text("column"))) rawName = descriptor.toObject().value(text("name")).toString();
        int excludedCount = 0;
        for (const auto source : rows) if (!rowUsed(source.toInt())) ++excludedCount;
        auto transformText = [&spec](const QString& key, double fallback) -> QString {
            const auto value = spec.value(key);
            if (value.isUndefined()) return QString::number(fallback);
            if (value.isDouble() && std::isfinite(value.toDouble())) return QString::number(value.toDouble(), 'g', 15);
            QString original;
            if (value.isString()) original = value.toString().isEmpty() ? text("빈 값") : value.toString();
            else { const auto encoded = QJsonDocument(QJsonArray{value}).toJson(QJsonDocument::Compact); original = QString::fromUtf8(encoded.mid(1, encoded.size() - 2)); }
            return original + text(" (미완성)");
        };
        channelSummary->setText(text("원열: ") + rawName + text("\n원값 단위: ") + rawUnitLabel(spec)
            + text("\n준비 후 채널 단위: ") + spec.value(text("unit")).toString()
            + text("\n") + CaelabDataSettingsDialog::physicalLabel(text("measure"), spec.value(text("measure")).toString())
            + text("  ") + CaelabDataSettingsDialog::physicalLabel(text("component"), spec.value(text("component")).toString())
            + text("\n배율: ") + transformText(text("scale"), 1) + text("   오프셋: ") + transformText(text("offset"), 0)
            + text("\n계산 제외: ") + QString::number(excludedCount) + text("행")
            + text("\n표와 곡선: 교정·변환 전 원값\n변환은 자료 준비에 적용"));
        window->m_propertiesDock->setWindowTitle(text("채널과 계산 사용"));
        window->stackedWidget->setCurrentWidget(channelPane); channelPane->show();
    }
    void selectSourceColumn(int index) {
        if (!connected() || index < 1 || index > rawColumns.size()) return;
        const auto key = rawColumns[index - 1].toObject().value(text("key"));
        const auto columns = draft.value(text("mapping")).toObject().value(text("columns")).toObject();
        sourceColumnSection = CaelabDataSettingsDialog::Section::Channel;
        if (columns.value(channel).toObject().value(text("column")) != key)
            for (auto it = columns.begin(); it != columns.end(); ++it) if (it.value().toObject().value(text("column")) == key) { channel = it.key(); break; }
        if (columns.value(channel).toObject().value(text("column")) != key && columns.value(channel).toObject().value(text("axis")).toObject().value(text("column")) == key) sourceColumnSection = CaelabDataSettingsDialog::Section::Axis;
        refreshEngineeringView(); showChannelPane();
    }
    void attachInteraction() {
        if (!connected() || !sheet || !sourceCurve || !sourcePlot || !sourceWorksheet) return;
        sheet->setProperty("caelab_source_view_order", true);
        const bool wasUndoAware = connectedProject->isUndoAware(), wasChanged = connectedProject->isChanged(); connectedProject->setUndoAware(false);
        if (!displayCache || displayCache->project() != connectedProject) {
            auto* cache = new Spreadsheet(text("곡선 표시 자료"));
            cache->setColumnCount(3); cache->setRowCount(rows.size()); cache->setReadOnly(true);
            {
                const QSignalBlocker block(window->m_projectExplorer);
                connectedProject->addChild(cache); cache->setHidden(true);
            }
            displayCache = cache;
            window->m_projectExplorer->setCurrentAspect(sheet);
        }
        displayCache->setName(text("곡선 표시 자료")); displayCache->setHidden(true);
        if (displayCache->hasMdiSubWindow()) {
            displayCache->suppressDeletion(true);
            displayCache->dockWidget()->toggleView(false);
            displayCache->suppressDeletion(false);
        }
        sheet->setColumnCount(rawColumns.size() + 3);
        for (int column = rawColumns.size() + 1; column < sheet->columnCount(); ++column) {
            sheet->column(column)->setColumnMode(AbstractColumn::ColumnMode::Text);
            sheet->column(column)->setName(column == rawColumns.size() + 1 ? text("계산") : text("품질"));
        }
        connectedProject->setUndoAware(wasUndoAware); connectedProject->setChanged(wasChanged);
        sourceCurve->setProperty("caelab_data_curve", true); sourceCurve->installEventFilter(this);
        QObject::disconnect(selectionConnection); QObject::disconnect(pointsConnection);
        QObject::disconnect(headerConnection); QObject::disconnect(headerEditConnection);
        QObject::disconnect(xSourceConnection); QObject::disconnect(ySourceConnection);
        auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
        if (auto* table = view ? view->findChild<QTableView*>() : nullptr) {
            if (!table->property("caelab_source_layout_connected").toBool()) {
                const QPointer<Spreadsheet> source = sheet;
                auto changed = [this, source] {
                    if (!refreshingView && connected() && sheet == source) connectedProject->setChanged(true);
                };
                QObject::connect(table->horizontalHeader(), &QHeaderView::sectionMoved, this, changed);
                QObject::connect(table->horizontalHeader(), &QHeaderView::sectionResized, this, changed);
                table->setProperty("caelab_source_layout_connected", true);
            }
            selectionConnection = QObject::connect(table->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this, view] {
                if (selecting || refreshingView) return;
                if (!view->findChild<QTableView*>()->selectionModel()->selectedColumns().isEmpty()) return;
                QSet<int> sources;
                for (int row = 0; row < sheet->rowCount(); ++row) if (view->isRowSelected(row, false)) sources.insert(static_cast<int>(sheet->column(0)->valueAt(row)));
                selectedSources = sources; drawOverlays();
            });
            headerConnection = QObject::connect(table->horizontalHeader(), &QHeaderView::sectionClicked, this, [this](int index) { selectSourceColumn(index); });
            headerEditConnection = QObject::connect(table->horizontalHeader(), &QHeaderView::sectionDoubleClicked, this, [this](int index) { selectSourceColumn(index); if (index > 0 && index <= rawColumns.size()) { nextMappingSection = sourceColumnSection; settingsAction->trigger(); } });
            table->addActions({settingsAction, excludeAction, applyAction, prepareAction, materialAction, discussAction});
            table->setContextMenuPolicy(Qt::ActionsContextMenu);
            table->horizontalHeader()->addAction(settingsAction); table->horizontalHeader()->setContextMenuPolicy(Qt::ActionsContextMenu);
        }
        auto guardSource = [this](const AbstractColumn*) {
            if (!refreshingView && connected() && sourceCurve && displayCache &&
                (sourceCurve->xColumn() != displayCache->column(1) || sourceCurve->yColumn() != displayCache->column(2))) {
                refreshEngineeringView();
                showChannelPane();
                if (!sourceEditQueued) {
                    sourceEditQueued = true;
                    QTimer::singleShot(0, this, [this] { sourceEditQueued = false; nextMappingSection = CaelabDataSettingsDialog::Section::Channel; settingsAction->trigger(); });
                }
            }
        };
        xSourceConnection = QObject::connect(sourceCurve, &XYCurve::xColumnChanged, this, guardSource);
        ySourceConnection = QObject::connect(sourceCurve, &XYCurve::yColumnChanged, this, guardSource);
        pointsConnection = QObject::connect(sourceCurve, &XYCurve::pointsUpdated, this, [this] { if (!refreshingView) drawOverlays(); });
        if (auto* curveView = dynamic_cast<WorksheetView*>(sourceWorksheet->view())) curveView->viewport()->installEventFilter(this);
    }
    void selectSources(const QSet<int>& sources) {
        if (!sheet) return;
        selectedSources = sources; selecting = true;
        if (auto* view = dynamic_cast<SpreadsheetView*>(sheet->view())) {
            if (auto* table = view->findChild<QTableView*>()) {
                QItemSelection selected;
                for (int row = 0; row < sheet->rowCount(); ++row) if (sources.contains(static_cast<int>(sheet->column(0)->valueAt(row))))
                    selected.select(table->model()->index(row, 0), table->model()->index(row, sheet->columnCount() - 1));
                table->selectionModel()->clear();
                table->selectionModel()->select(selected, QItemSelectionModel::ClearAndSelect);
                if (!selected.isEmpty()) table->selectionModel()->setCurrentIndex(selected.first().topLeft(), QItemSelectionModel::NoUpdate);
            }
        }
        selecting = false; drawOverlays();
        window->statusBar()->showMessage(text("원행 ") + QString::number(sources.size()) + text("개 선택"));
    }
    void drawOverlays() {
        if (refreshingView || !sourceCurve || !sourcePlot || !displayCache) return;
        if (markerOwner && markerOwner == sourceCurve) qDeleteAll(markers);
        markers.clear(); markerOwner = sourceCurve;
        const auto selection = channelSpec().value(text("row_selection")).toObject();
        const auto poor = selection.value(text("quality_rows")).toArray(), excluded = selection.value(text("exclude_rows")).toArray();
        for (int row = 0; row < displayCache->rowCount(); ++row) {
            const int source = static_cast<int>(displayCache->column(0)->valueAt(row)); bool visible = false;
            const auto point = sourcePlot->coordinateSystem(sourceCurve->coordinateSystemIndex())->mapLogicalToScene(QPointF(displayCache->column(1)->valueAt(row), displayCache->column(2)->valueAt(row)), visible);
            if (!visible) continue;
            auto decorate = [&](QGraphicsItem* marker) {
                marker->setParentItem(sourceCurve->graphicsItem()); marker->setPos(point);
                marker->setFlag(QGraphicsItem::ItemIgnoresTransformations); marker->setAcceptedMouseButtons(Qt::NoButton); marker->setZValue(1000); markers.append(marker);
            };
            if (selectedSources.contains(source)) { auto* marker = new QGraphicsEllipseItem(-7, -7, 14, 14); marker->setPen(QPen(QColor(0, 113, 188), 2)); decorate(marker); }
            if (poor.contains(source)) { auto* marker = new QGraphicsRectItem(-4, -4, 8, 8); marker->setPen(QPen(QColor(181, 121, 0), 2)); decorate(marker); }
            if (!rowUsed(source)) {
                for (int sign : {-1, 1}) { auto* marker = new QGraphicsLineItem(-5, -5 * sign, 5, 5 * sign); marker->setPen(QPen(QColor(170, 50, 40), 2)); decorate(marker); }
            }
        }
    }
    void refreshEngineeringView() {
        if (refreshingView || !connected() || !sheet || !sourceCurve || !displayCache) return;
        refreshingView = true;
        const bool dirty = connectedProject->isChanged(), undoAware = connectedProject->isUndoAware(); connectedProject->setUndoAware(false);
        const auto spec = channelSpec(), selection = spec.value(text("row_selection")).toObject(), axisSpec = spec.value(text("axis")).toObject();
        int x = -1, y = -1;
        for (int column = 0; column < rawColumns.size(); ++column) {
            const auto key = rawColumns[column].toObject().value(text("key"));
            if (key == axisSpec.value(text("column"))) x = column;
            if (key == spec.value(text("column"))) y = column;
        }
        for (int column = 0; column < sheet->columnCount(); ++column) sheet->column(column)->setPlotDesignation(AbstractColumn::PlotDesignation::NoDesignation);
        if (x >= 0) sheet->column(x + 1)->setPlotDesignation(AbstractColumn::PlotDesignation::X);
        if (y >= 0) sheet->column(y + 1)->setPlotDesignation(AbstractColumn::PlotDesignation::Y);
        displayCache->column(0)->setName(text("원행")); displayCache->column(0)->setPlotDesignation(AbstractColumn::PlotDesignation::NoDesignation);
        displayCache->column(1)->setName(axisSpec.value(text("name")).toString(text("가로축")) + text(" (") + rawUnitLabel(axisSpec) + text(")"));
        displayCache->column(1)->setPlotDesignation(AbstractColumn::PlotDesignation::X);
        displayCache->column(2)->setName(channel + text(" (") + rawUnitLabel(spec) + text(")"));
        displayCache->column(2)->setPlotDesignation(AbstractColumn::PlotDesignation::Y);
        QVector<double> identities, xs, ys;
        for (int row = 0; row < rows.size(); ++row) {
            const int source = rows[row].toInt(); identities.append(source);
            const bool hidden = selection.value(text("display_hidden_rows")).toArray().contains(source);
            xs.append(hidden ? std::numeric_limits<double>::quiet_NaN() : rawNumber(x, row));
            ys.append(hidden ? std::numeric_limits<double>::quiet_NaN() : rawNumber(y, row));
        }
        displayCache->setRowCount(rows.size()); displayCache->column(0)->setValues(identities); displayCache->column(1)->setValues(xs); displayCache->column(2)->setValues(ys);
        sourceCurve->setXColumn(displayCache->column(1)); sourceCurve->setYColumn(displayCache->column(2));
        if (sourcePlot) for (auto* axis : sourcePlot->children<Axis>()) {
            const QString label = axis->orientation() == WorksheetElement::Orientation::Horizontal
                ? QString(axisSpec.value(text("name")).toString() + text(" (") + rawUnitLabel(axisSpec) + text(")"))
                : QString(channel + text(" (") + rawUnitLabel(spec) + text(")"));
            axis->title()->setText(TextLabel::TextWrapper(QString(text("<span style=\"font-size:8pt\">") + label.toHtmlEscaped() + text("</span>")), TextLabel::Mode::Text, true));
        }
        auto* view = dynamic_cast<SpreadsheetView*>(sheet->view()); auto* table = view ? view->findChild<QTableView*>() : nullptr;
        refreshSourceHeaders();
        for (int row = 0; row < sheet->rowCount(); ++row) {
            const int source = static_cast<int>(sheet->column(0)->valueAt(row));
            sheet->column(rawColumns.size() + 1)->setTextAt(row, rowUsed(source) ? text("포함") : text("제외"));
            sheet->column(rawColumns.size() + 2)->setTextAt(row, selection.value(text("quality_rows")).toArray().contains(source) ? text("확인 필요") : QString());
            if (table) table->setRowHidden(row, selection.value(text("display_hidden_rows")).toArray().contains(source));
        }
        connectedProject->setUndoAware(undoAware); connectedProject->setChanged(dirty); refreshingView = false; drawOverlays();
        QTimer::singleShot(0, this, [this] { refreshExplorerNames(); });
        if (channelPane && window->stackedWidget->currentWidget() == channelPane) showChannelPane();
    }
    void editSelectedRows(const QString& field, bool clear = false, bool all = false) {
        if (!connected() || inputConflict || !pendingApply.isEmpty() || pendingView()) throw std::runtime_error("Finish recovery or pending work before editing local row settings.");
        auto mapping = draft.value(text("mapping")).toObject(), channels = mapping.value(text("columns")).toObject(), spec = channels.value(channel).toObject();
        auto selection = spec.value(text("row_selection")).toObject(); auto values = selection.value(field).toArray();
        if (field == text("exclude_rows")) { values = {}; for (const auto source : rows) if (!rowUsed(source.toInt())) values.append(source); selection.remove(text("include_ranges")); selection.remove(text("exclude_ranges")); }
        if (all) values = {};
        else if (clear) { QJsonArray kept; for (const auto value : values) if (!selectedSources.contains(value.toInt())) kept.append(value); values = kept; }
        else for (int source : selectedSources) if (!values.contains(source)) values.append(source);
        selection.insert(field, values); spec.insert(text("row_selection"), selection); channels.insert(channel, spec); mapping.insert(text("columns"), channels);
        auto edited = draft; edited.insert(text("mapping"), mapping); connectedProject->undoStack()->push(new DraftChange(this, edited));
    }
    void writeSourceOrder() {
        if (!connected() || !sheet) return;
        const bool undoAware = connectedProject->isUndoAware(); connectedProject->setUndoAware(false); refreshingView = true;
        QVector<double> identities; for (int index : displayOrder) identities.append(rows[index].toDouble());
        sheet->column(0)->setValues(identities);
        for (int column = 0; column < rawColumns.size(); ++column) {
            const auto descriptor = rawColumns[column].toObject(); const auto values = descriptor.value(text("values")).toArray();
            bool textual = false;
            for (const auto value : values) if (value.isString()) { bool valid = false; value.toString().toDouble(&valid); if (!valid && value.toString() != text("nan") && value.toString() != text("inf") && value.toString() != text("-inf")) textual = true; }
            auto* target = sheet->column(column + 1); target->setName(descriptor.value(text("name")).toString());
            if (textual) {
                target->setColumnMode(AbstractColumn::ColumnMode::Text); QVector<QString> ordered;
                for (int index : displayOrder) { const auto value = index < values.size() ? values[index] : QJsonValue(); ordered.append(value.isString() ? value.toString() : value.isDouble() ? QString::number(value.toDouble(), 'g', 17) : QString()); }
                target->setText(ordered);
            } else {
                target->setColumnMode(AbstractColumn::ColumnMode::Double); QVector<double> ordered;
                for (int index : displayOrder) ordered.append(rawNumber(column, index)); target->setValues(ordered);
            }
        }
        refreshingView = false; connectedProject->setUndoAware(undoAware); refreshEngineeringView(); selectSources(selectedSources);
    }
    void sortRows(int column, bool descending) {
        if (!connected() || !pendingApply.isEmpty() || pendingView()) throw std::runtime_error("먼저 진행 중인 저장 또는 적용을 마치세요.");
        std::stable_sort(displayOrder.begin(), displayOrder.end(), [this, column, descending](int left, int right) {
            int compared = 0;
            if (column < 0) compared = rows[left].toInt() < rows[right].toInt() ? -1 : rows[left].toInt() > rows[right].toInt() ? 1 : 0;
            else {
                const auto a = rawNumber(column, left), b = rawNumber(column, right);
                if (std::isfinite(a) && std::isfinite(b)) compared = a < b ? -1 : a > b ? 1 : 0;
                else { const auto values = rawColumns[column].toObject().value(text("values")).toArray(); compared = QString::localeAwareCompare(left < values.size() ? values[left].toVariant().toString() : QString(), right < values.size() ? values[right].toVariant().toString() : QString()); }
            }
            return descending ? compared > 0 : compared < 0;
        });
        writeSourceOrder(); connectedProject->setChanged(true);
        window->statusBar()->showMessage(text("표 보기만 정렬했습니다. 원행과 Core 입력은 유지됩니다."));
    }
    void editMapping(CaelabDataSettingsDialog::Section section = CaelabDataSettingsDialog::Section::All) {
        if (!connected() || inputConflict || !pendingApply.isEmpty() || pendingView()) throw std::runtime_error("먼저 연결과 저장 상태를 확인하세요.");
        CaelabDataSettingsDialog dialog(draft, rawColumns, channel, window);
        dialog.focusSection(section);
        if (dialog.exec() != QDialog::Accepted) return;
        const auto edited = dialog.editedDraft();
        if (edited != draft) connectedProject->undoStack()->push(new DraftChange(this, edited, dialog.selectedChannel()));
        else { channel = dialog.selectedChannel(); refreshEngineeringView(); }
        showChannelPane(); syncLocks();
    }
    int chooseDocument(const QString& title, const QString& label, const QStringList& names) {
        QInputDialog dialog(window); dialog.setWindowTitle(title); dialog.setLabelText(label);
        dialog.setComboBoxItems(names); dialog.setComboBoxEditable(false);
        if (dialog.exec() != QDialog::Accepted) return -1;
        auto* choices = dialog.findChild<QComboBox*>(); return choices ? choices->currentIndex() : -1;
    }
    void openCoreData() {
        if (!pendingApply.isEmpty() || pendingView()) throw std::runtime_error("진행 중인 적용 또는 저장을 먼저 마치세요.");
        const auto documents = request(text("/api/workbench/documents")).value(text("documents")).toArray();
        QStringList names, identifiers;
        for (const auto item : documents) { const auto doc = item.toObject(); if (doc.value(text("kind")) == text("data")) { names.append(doc.value(text("title")).toString()); identifiers.append(doc.value(text("id")).toString()); } }
        if (names.isEmpty()) throw std::runtime_error("열 자료 문서가 없습니다. 원자료 파일을 여세요.");
        const int selected = chooseDocument(text("자료 열기"), text("자료 문서"), names);
        if (selected < 0 || selected >= identifiers.size()) return;
        const auto target = identifiers.value(selected);
        if (connected() && target == identifier) return;
        const auto document = request(text("/api/workbench/documents/") + target);
        auto lease = prepareActivation(document, target);
        if (lease->forwarded) return;
        if (!window->newProject()) return;
        identifier = target; loadedBinding = {}; inputConflict = false; load(document, std::move(lease));
    }
    void openSourceFile(const QString& selectedPath = {}, int selectedHeaders = -1) {
        if (!pendingApply.isEmpty() || pendingView()) throw std::runtime_error("진행 중인 적용 또는 저장을 먼저 마치세요.");
        const auto path = selectedPath.isEmpty() ? QFileDialog::getOpenFileName(window, text("원자료 열기"), QString(), text("원자료 (*.csv *.txt *.dat *.npz);;모든 파일 (*)")) : selectedPath;
        if (path.isEmpty()) return;
        bool accepted = selectedHeaders >= 0;
        const int headers = selectedHeaders >= 0 ? selectedHeaders : QFileInfo(path).suffix().compare(text("npz"), Qt::CaseInsensitive) == 0 ? 0 : QInputDialog::getInt(window, text("읽기 설정"), text("머리말 줄 수"), 1, 0, 100000, 1, &accepted);
        if (QFileInfo(path).suffix().compare(text("npz"), Qt::CaseInsensitive) != 0 && !accepted) return;
        QFile source(path);
        if (!source.open(QIODevice::ReadOnly) || source.size() <= 0 || source.size() > 16 * 1024 * 1024) throw std::runtime_error("비어 있지 않은 16 MiB 이하 원자료 파일을 선택하세요.");
        if (!window->newProject()) return;
        QNetworkRequest query{QUrl(service + text("/api/workbench/upload"))}; query.setTransferTimeout(30000);
        query.setRawHeader(QByteArrayLiteral("X-CAE-Token"), request(text("/api/overview")).value(text("token")).toString().toUtf8());
        query.setRawHeader(QByteArrayLiteral("X-File-Name"), QUrl::toPercentEncoding(QFileInfo(path).fileName()));
        query.setRawHeader(QByteArrayLiteral("X-File-Name-Encoding"), QByteArrayLiteral("percent-utf8")); query.setHeader(QNetworkRequest::ContentTypeHeader, text("application/octet-stream"));
        auto* reply = network.post(query, source.readAll()); QEventLoop loop; QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit); loop.exec(QEventLoop::ExcludeUserInputEvents);
        const auto upload = QJsonDocument::fromJson(reply->readAll()).object(); const bool succeeded = reply->error() == QNetworkReply::NoError; reply->deleteLater();
        if (!succeeded || upload.value(text("id")).toString().isEmpty()) throw std::runtime_error("원자료를 등록하지 못했습니다. 원본 파일은 유지됩니다.");
        const QJsonObject opened{{text("kind"), text("data")}, {text("title"), QFileInfo(path).completeBaseName()}};
        baseline = request(text("/api/workbench/documents/open"), &opened); identifier = baseline.value(text("id")).toString(); loadedBinding = {}; inputConflict = false;
        draft = baseline.value(text("draft")).toObject(); draft.insert(text("data_id"), upload.value(text("id")));
        auto mapping = draft.value(text("mapping")).toObject(); mapping.insert(text("skip_header"), headers); draft.insert(text("mapping"), mapping);
        attachProject(); apply(); load();
        window->statusBar()->showMessage(text("원자료를 열었습니다. 열과 단위에서 물리량을 지정하세요. 자료 준비는 별도로 실행합니다."));
    }
    QJsonObject command(const QString& operation, const QJsonObject& arguments = {}) {
        if (!prepareJob.isEmpty()) throw std::runtime_error("자료 준비의 종료를 확인한 뒤 변경 또는 저장하세요.");
        if (!connected() || inputConflict) throw std::runtime_error("Reconnect or explicitly reload the preserved Core input before submitting another command.");
        if (pendingApply.isEmpty()) {
            const auto current = request(documentPath());
            if (current.value(text("session_id")) != baseline.value(text("session_id")) || current.value(text("generation")) != baseline.value(text("generation")))
                throw std::runtime_error("Core input changed. The local buffer has been preserved; reopen or recover it.");
            pendingApply = QJsonObject{{text("operation"), operation}, {text("arguments"), arguments},
                {text("session_id"), baseline.value(text("session_id"))}, {text("expected_generation"), baseline.value(text("generation"))},
                {text("command_id"), QString(text("C") + QUuid::createUuid().toString(QUuid::Id128))}};
        }
        if (pendingApply.value(text("operation")) != operation) throw std::runtime_error("Retry the original pending command first.");
        const auto receipt = request(documentPath() + text("/commands"), &pendingApply);
        confirmedReceipt = receipt;
        const auto acknowledged = receipt.value(text("document")).toObject();
        const auto current = request(documentPath());
        for (const auto* key : {"session_id", "generation", "input_revision", "draft"})
            if (current.value(text(key)) != acknowledged.value(text(key))) {
                conflictCurrent = current; preserveCommandConflict();
                throw std::runtime_error("The original command is acknowledged, but Core input has changed. The local project, request and acknowledgement are preserved in a recovery file; explicitly reload or close without overwriting Core.");
            }
        baseline = current; pendingApply = {};
        syncLocks();
        return receipt;
    }
    void apply() {
        command(text("data.update"), QJsonObject{{text("draft"), draft}});
        window->statusBar()->showMessage(text("변경을 적용했습니다. 자료 준비는 별도로 실행하세요."));
    }
    void attachProject() {
        QObject::disconnect(saveStateConnection);
        connectedProject = window->project();
        boundProject = connectedProject;
        auto* owner = connectedProject.data();
        saveStateConnection = QObject::connect(owner, &Project::requestSaveState, this, [this, owner](QXmlStreamWriter* writer) {
            if (!serializing || owner != connectedProject || owner != window->project()) return;
            auto* view = sheet ? dynamic_cast<SpreadsheetView*>(sheet->view()) : nullptr;
            if (auto* table = view ? view->findChild<QTableView*>() : nullptr)
                pendingBinding.insert(text("source_header_state"), QString::fromLatin1(table->horizontalHeader()->saveState().toBase64()));
            writer->writeTextElement(text("caelab_data_binding"), QString::fromLatin1(QJsonDocument(pendingBinding).toJson(QJsonDocument::Compact).toBase64()));
        });
    }
    QJsonObject fileBinding(const QString& path) const {
        QFile file(path); if (!file.open(QIODevice::ReadOnly)) return {};
        QXmlStreamReader reader(&file);
        while (!reader.atEnd()) {
            reader.readNext();
            if (reader.isStartElement() && reader.name() == text("caelab_data_binding"))
                return QJsonDocument::fromJson(QByteArray::fromBase64(reader.readElementText().toLatin1())).object();
        }
        return {};
    }
    void restoreBinding(const QString& path, bool startup = false) {
        const bool prepared = !openingBinding.isEmpty() && openingPath == QFileInfo(path).absoluteFilePath();
        const auto binding = prepared ? openingBinding : fileBinding(path);
        if (binding.isEmpty()) return;
        const auto acknowledgement = binding.value(text("document")).toObject();
        // A startup file has already been read by MainWin::initGUI, before the
        // bridge exists. Preserve its Core-save guard even if reconnect fails.
        if (startup) { boundProject = window->project(); loadedBinding = binding; }
        const auto oldService = service, oldIdentifier = identifier;
        const auto targetService = service.isEmpty() ? binding.value(text("service_url")).toString() : service;
        const auto target = acknowledgement.value(text("id")).toString();
        try {
            const auto current = prepared ? openingDocument : request(text("/api/workbench/documents/") + target, nullptr, targetService);
            if (current.value(text("input_revision")) != acknowledgement.value(text("input_revision")) || current.value(text("draft")) != acknowledgement.value(text("draft")))
                throw std::runtime_error("The saved native view refers to an older Core input. Its file is preserved; reopen the matching Core revision explicitly.");
            auto lease = prepared ? std::move(openingLease) : prepareActivation(current, target, targetService);
            if (lease->forwarded) {
                if (startup) QTimer::singleShot(0, window, &QWidget::close);
                return;
            }
            service = targetService; identifier = target; boundProject = window->project(); loadedBinding = binding;
            baseline = current; draft = current.value(text("draft")).toObject(); savedAck = acknowledgement;
            inputConflict = false;
            importedReference = binding.value(text("result_reference")).toObject();
            channel = binding.value(text("response")).toString(); rows = binding.value(text("source_rows")).toArray();
            ++loadEpoch; attachProject();
            sheet.clear(); sourceWorksheet.clear(); displayCache.clear(); sourceCurve.clear(); sourcePlot.clear();
            for (auto* part : connectedProject->children<Spreadsheet>(AbstractAspect::ChildIndexFlag::IncludeHidden)) {
                if ((!binding.value(text("source_uuid")).toString().isEmpty() && part->uuid().toString() == binding.value(text("source_uuid"))) ||
                    (binding.value(text("source_uuid")).toString().isEmpty() && (part->name() == text("원자료") || part->name() == text("Core source")))) sheet = part;
                if (part->uuid().toString() == binding.value(text("cache_uuid"))) displayCache = part;
            }
            for (auto* part : connectedProject->children<Worksheet>()) if ((!binding.value(text("worksheet_uuid")).toString().isEmpty() && part->uuid().toString() == binding.value(text("worksheet_uuid"))) ||
                (binding.value(text("worksheet_uuid")).toString().isEmpty() && (part->name() == text("응답 곡선") || part->name() == text("Core curve")))) sourceWorksheet = part;
            if (!sheet) throw std::runtime_error("The saved native source table is missing.");
            rawColumns = binding.value(text("source_identity")).toObject().value(text("columns")).toArray();
            displayOrder.clear(); selectedSources.clear();
            for (const auto value : binding.value(text("selected_source_rows")).toArray()) selectedSources.insert(value.toInt());
            for (int row = 0; row < sheet->rowCount(); ++row) {
                int original = -1;
                for (int index = 0; index < rows.size(); ++index) if (rows[index].toDouble() == sheet->column(0)->valueAt(row)) { original = index; break; }
                displayOrder.append(original);
            }
            for (int column = 0; column < rawColumns.size(); ++column) {
                auto descriptor = rawColumns[column].toObject(); QJsonArray values;
                for (int original = 0; original < qMin(rows.size(), descriptor.value(text("length")).toInt(rows.size())); ++original) {
                    const auto source = rows[original]; int index = -1;
                    for (int row = 0; row < sheet->rowCount(); ++row) if (sheet->column(0)->valueAt(row) == source.toDouble()) { index = row; break; }
                    values.append(index < 0 ? QJsonValue() : sheet->column(column + 1)->columnMode() == AbstractColumn::ColumnMode::Text ? QJsonValue(sheet->column(column + 1)->textAt(index)) : QJsonValue(sheet->column(column + 1)->valueAt(index)));
                }
                descriptor.insert(text("values"), values); rawColumns[column] = descriptor;
            }
            if (sourceWorksheet) {
                for (auto* plot : sourceWorksheet->children<CartesianPlot>()) for (auto* curve : plot->children<XYCurve>())
                    if ((!binding.value(text("curve_uuid")).toString().isEmpty() && curve->uuid().toString() == binding.value(text("curve_uuid"))) || binding.value(text("curve_uuid")).toString().isEmpty()) { sourceCurve = curve; sourcePlot = plot; }
            }
            analysisLayout = false;
            attachInteraction();
            if (auto* view = dynamic_cast<SpreadsheetView*>(sheet->view())) if (auto* table = view->findChild<QTableView*>()) {
                const QScopedValueRollback<bool> restoring(refreshingView, true);
                const auto state = QByteArray::fromBase64(binding.value(text("source_header_state")).toString().toLatin1());
                if (!state.isEmpty() && !table->horizontalHeader()->restoreState(state))
                    throw std::runtime_error("The saved native source column layout could not be restored. The file remains unchanged.");
                // Loaded native columns already retain widths. Old files have
                // no visual-order state; keep their existing logical view.
                table->setProperty("caelab_source_order_set", true);
                for (int index = 0; index < sheet->columnCount(); ++index) sheet->column(index)->setProperty("caelab_source_width_set", true);
            }
            refreshEngineeringView(); selectSources(selectedSources);
            foldNativeTools();
            window->m_projectExplorer->setDataWorkspaceMode(true);
            QTimer::singleShot(0, this, [this] { refreshExplorerNames(); });
            window->statusBar()->showMessage(text("Saved Core input and native view reopened. No calculation was submitted."));
            commitActivation(std::move(lease));
        } catch (...) { connectedProject.clear(); service = oldService; identifier = oldIdentifier; throw; }
    }
    QString recoveryPath() const {
        const auto folder = QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + text("/caelab-data-recovery");
        QDir().mkpath(folder); return folder + text("/") + identifier + text(".json");
    }
    void preserveCommandConflict() {
        const auto previousBinding = pendingBinding;
        pendingBinding = QJsonObject{{text("service_url"), service}, {text("document"), baseline}, {text("response"), channel}, {text("source_rows"), rows}};
        QByteArray xml; QBuffer buffer(&xml); buffer.open(QIODevice::WriteOnly); QXmlStreamWriter writer(&buffer);
        serializing = true; connectedProject->save(QPixmap(), &writer); serializing = false;
        pendingBinding = previousBinding;
        const QJsonObject journal{{text("kind"), text("command_conflict")}, {text("request"), pendingApply},
            {text("receipt"), confirmedReceipt}, {text("current_document"), conflictCurrent}, {text("baseline"), baseline},
            {text("local_draft"), draft}, {text("xml"), QString::fromLatin1(xml.toBase64())}, {text("service_url"), service}};
        conflictJournal = recoveryPath() + text(".conflict-") + QUuid::createUuid().toString(QUuid::Id128) + text(".json");
        QSaveFile file(conflictJournal);
        if (writer.hasError() || !file.open(QIODevice::WriteOnly) || file.write(QJsonDocument(journal).toJson()) < 0 || !file.commit())
            throw std::runtime_error("The confirmed command and local buffer are still in this window; its recovery file could not be committed. Retry before closing.");
        inputConflict = true; pendingApply = {}; pendingBinding = {}; pendingXml.clear();
        connectedProject->setChanged(true); syncLocks();
    }
    void writeRecovery() {
        QSaveFile file(recoveryPath());
        if (!file.open(QIODevice::WriteOnly)) throw std::runtime_error("Core is saved; recovery journal could not be written. Keep this window open and retry.");
        const QJsonObject journal{{text("path"), pendingPath}, {text("binding"), pendingBinding}, {text("xml"), QString::fromLatin1(pendingXml.toBase64())}};
        if (file.write(QJsonDocument(journal).toJson()) < 0 || !file.commit()) throw std::runtime_error("Core is saved; recovery journal could not be committed. Keep this window open.");
    }
    bool commitView(bool injectFailure = false) {
        if (!connected() || pendingXml.isEmpty()) throw std::runtime_error("No connected exact view snapshot is pending.");
        writeRecovery();
        if (injectFailure) throw std::runtime_error("Acceptance injected view-write failure after Core save; the exact snapshot is preserved.");
        QSaveFile file(pendingPath);
        if (!file.open(QIODevice::WriteOnly) || file.write(pendingXml) != pendingXml.size() || !file.commit())
            throw std::runtime_error("Core is saved; native view replacement failed. The prior file and exact retry snapshot are preserved.");
        const auto ack = pendingBinding.value(text("document")).toObject();
        const auto current = request(documentPath());
        if (current.value(text("input_revision")) != ack.value(text("input_revision")) || current.value(text("draft")) != ack.value(text("draft")))
            throw std::runtime_error("The exact older view was written, but Core input has since changed. The buffer and recovery snapshot remain available.");
        savedAck = ack; baseline = current; connectedProject->setFileName(pendingPath);
        const bool laterChanges = current.value(text("dirty")).toBool();
        connectedProject->setChanged(laterChanges); window->undoStackIndexLastSave = connectedProject->undoStack()->index();
        QFile::remove(recoveryPath()); pendingXml.clear(); pendingBinding = {}; pendingPath.clear(); syncLocks();
        window->updateTitleBar();
        window->statusBar()->showMessage(laterChanges ? text("The requested exact view is saved. Core has later unsaved result changes.") : text("Core saved and exact native view replaced successfully."));
        return true;
    }
    void beginSave(const QString& path) {
        if (!connected() || inputConflict) throw std::runtime_error("This bound project could not verify its Core input. Its original binding and file are preserved; reconnect before saving.");
        if (!pendingXml.isEmpty()) return;
        if (draft != baseline.value(text("draft")).toObject()) apply();
        auto* owner = connectedProject.data();
        pendingPath = path;
        if (pendingBinding.isEmpty()) {
            const auto receipt = command(text("document.save"));
            pendingBinding.insert(text("document"), receipt.value(text("document")));
        }
        const auto ack = pendingBinding.value(text("document")).toObject();
        if (!owner || connectedProject != owner || window->project() != owner) throw std::runtime_error("The native project changed while saving. Keep the exact Core receipt.");
        if (ack.value(text("saved_revision")).isNull() || ack.value(text("dirty")).toBool()) throw std::runtime_error("Core did not confirm a saved revision.");
        if (!importedReference.value(text("job_id")).toString().isEmpty())
            importedReference = request(documentPath() + text("/result-reference/") + importedReference.value(text("job_id")).toString());
        const auto raw = request(documentPath() + text("/source-table?start=0&count=1"));
        if (raw.value(text("input_revision")) != ack.value(text("input_revision")) || raw.value(text("mapping")) != ack.value(text("draft")).toObject().value(text("mapping")))
            throw std::runtime_error("Core input changed after its save acknowledgement. Keep the exact acknowledgement and local project for recovery.");
        pendingBinding = QJsonObject{{text("service_url"), service}, {text("document"), ack}, {text("response"), channel},
            {text("source_rows"), rows}, {text("source_identity"), raw},
            {text("result_reference"), importedReference}};
        pendingBinding.insert(text("source_uuid"), sheet ? sheet->uuid().toString() : QString());
        pendingBinding.insert(text("worksheet_uuid"), sourceWorksheet ? sourceWorksheet->uuid().toString() : QString());
        pendingBinding.insert(text("curve_uuid"), sourceCurve ? sourceCurve->uuid().toString() : QString());
        pendingBinding.insert(text("cache_uuid"), displayCache ? displayCache->uuid().toString() : QString());
        QJsonArray chosenRows; for (int source : selectedSources) chosenRows.append(source);
        pendingBinding.insert(text("selected_source_rows"), chosenRows);
        owner->setSaveData(true); owner->setFileCompression(false);
        owner->setDockWidgetState(QString::fromUtf8(window->m_dockManagerContent->saveState()));
        if (owner->saveDefaultDockWidgetState()) owner->setDefaultDockWidgetState(QString::fromUtf8(window->m_dockManagerMain->saveState()));
        QBuffer buffer(&pendingXml); buffer.open(QIODevice::WriteOnly); QXmlStreamWriter writer(&buffer);
        serializing = true; owner->save(QPixmap(), &writer); serializing = false;
        if (writer.hasError()) throw std::runtime_error("Core is saved; native XML serialization failed.");
        owner->setChanged(true); syncLocks();
    }
    void recoverSave(const QString& path) {
        QFile file(path); if (!file.open(QIODevice::ReadOnly)) throw std::runtime_error("The recovery snapshot could not be opened.");
        const auto journal = QJsonDocument::fromJson(file.readAll()).object();
        const auto xml = QByteArray::fromBase64(journal.value(text("xml")).toString().toLatin1());
        if (xml.isEmpty()) throw std::runtime_error("The recovery snapshot has no native view.");
        const auto temporary = QFileInfo(path).absolutePath() + text("/recovered-") + QUuid::createUuid().toString(QUuid::Id128) + text(".lml");
        QSaveFile view(temporary);
        if (!view.open(QIODevice::WriteOnly) || view.write(xml) != xml.size() || !view.commit()) throw std::runtime_error("The recovery view could not be staged.");
        if (!window->openProject(temporary)) throw std::runtime_error("The native recovery view could not be reopened.");
        if (journal.value(text("kind")) == text("command_conflict")) {
            baseline = journal.value(text("baseline")).toObject();
            draft = journal.value(text("local_draft")).toObject(); confirmedReceipt = journal.value(text("receipt")).toObject();
            conflictCurrent = journal.value(text("current_document")).toObject(); inputConflict = true; conflictJournal = path;
            window->statusBar()->showMessage(text("Conflict project and local edits recovered. Core remains unchanged; explicitly reload to choose current input."));
            return;
        }
        if (!connected()) restoreBinding(temporary);
        pendingBinding = journal.value(text("binding")).toObject(); pendingPath = journal.value(text("path")).toString(); pendingXml = xml;
        connectedProject->setChanged(true); syncLocks();
        window->statusBar()->showMessage(text("Exact failed-save snapshot recovered. Retry replaces the view without another Core save."));
    }
    void importData() {
        if (pendingView()) throw std::runtime_error("Complete the pending exact view save first.");
        if (draft != baseline.value(text("draft")).toObject()) throw std::runtime_error("Apply local settings before explicitly preparing data.");
        if (prepareJob.isEmpty()) {
            const auto receipt = command(text("data.import"));
            prepareJob = receipt.value(text("job")).toObject().value(text("id")).toString();
            if (prepareJob.isEmpty()) throw std::runtime_error("자료 준비가 실행 식별자를 반환하지 않았습니다.");
        }
        syncLocks();
        const auto jobId = prepareJob;
        QDialog progress(window); progress.setObjectName(text("caelab-data-prepare")); progress.setWindowTitle(text("자료 준비"));
        progress.setMinimumWidth(420);
        auto* layout = new QVBoxLayout(&progress);
        auto* label = new QLabel(text("자료 준비 상태를 확인하고 있습니다."), &progress); label->setWordWrap(true); layout->addWidget(label);
        auto* bar = new QProgressBar(&progress); bar->setRange(0, 0); layout->addWidget(bar);
        auto* buttons = new QDialogButtonBox(&progress);
        auto* cancel = buttons->addButton(text("취소 요청"), QDialogButtonBox::ActionRole); cancel->setObjectName(text("caelab-prepare-cancel"));
        auto* later = buttons->addButton(text("나중에 확인"), QDialogButtonBox::RejectRole); layout->addWidget(buttons);
        QObject::connect(later, &QPushButton::clicked, &progress, &QDialog::reject);
        bool cancellation = false, cancelSent = false, polling = false, terminal = false;
        QString failure, state;
        QObject::connect(cancel, &QPushButton::clicked, &progress, [&] { cancellation = true; cancel->setEnabled(false); label->setText(text("취소를 요청합니다. 실제 종료 확인 전까지 원자료와 이전 결과는 유지됩니다.")); });
        QTimer poll;
        QObject::connect(&poll, &QTimer::timeout, &progress, [&] {
            if (polling) return;
            polling = true; interactiveRequest = true;
            try {
                if (cancellation && !cancelSent) { const QJsonObject empty; request(text("/api/workbench/jobs/") + jobId + text("/cancel"), &empty); cancelSent = true; }
                const auto job = request(text("/api/workbench/jobs/") + jobId); lastPrepareJob = job;
                if (job.value(text("id")).toString() != jobId) throw std::runtime_error("다른 실행의 상태 응답을 받았습니다. 원 실행을 다시 확인하세요.");
                state = job.value(text("state")).toString();
                if (state == text("SUCCEEDED") || state == text("FAILED") || state == text("PARTIAL_FAILURE") || state == text("CANCELLED") || state == text("INTERRUPTED")) {
                    terminal = true; poll.stop(); progress.accept();
                } else {
                    label->setText(state == text("CANCEL_REQUESTED") ? text("취소 요청됨. 안전한 종료를 확인하고 있습니다.") : state == text("CLEANUP_PENDING") ? text("실행 정리가 아직 확인되지 않았습니다. 다시 확인하거나 나중에 확인할 수 있습니다.") : state == text("QUEUED") ? text("자료 준비 순서를 기다리고 있습니다.") : text("원자료를 준비하고 있습니다. 계산에 사용할 행과 단위를 적용합니다."));
                }
            } catch (const std::exception& error) { failure = QString::fromUtf8(error.what()); poll.stop(); progress.reject(); }
            interactiveRequest = false; polling = false;
        });
        poll.start(120); progress.exec(); poll.stop(); interactiveRequest = false;
        if (!failure.isEmpty()) throw std::runtime_error((text("자료 준비 상태를 확인하지 못했습니다. 취소는 확정되지 않았습니다. ‘다시 시도’로 같은 실행을 확인하세요. ") + failure).toUtf8().constData());
        if (!terminal) { window->statusBar()->showMessage(text("자료 준비는 계속 보존됩니다. ‘다시 시도’로 같은 실행을 확인하세요. 창 닫기는 취소 요청이 아닙니다.")); return; }
        if (state == text("SUCCEEDED")) {
            const auto current = request(documentPath());
            for (const auto* key : {"session_id", "generation", "input_revision", "draft"})
                if (current.value(text(key)) != baseline.value(text(key))) { prepareJob.clear(); inputConflict = true; syncLocks(); throw std::runtime_error("준비 중 Core 입력이 바뀌었습니다. 이전 실행과 원자료는 보존됩니다. 원자료를 다시 읽어 현재 입력을 확인하세요."); }
            baseline = current;
            importedReference = QJsonObject{{text("document_id"), identifier}, {text("job_id"), jobId}};
            connectedProject->setChanged(true);
            window->statusBar()->showMessage(text("자료 준비가 완료됐습니다. 저장한 뒤 재료에서 사용으로 정확한 결과를 검토하세요."));
        } else window->statusBar()->showMessage(state == text("CANCELLED") ? text("자료 준비 취소가 확인됐습니다. 원자료와 이전 결과는 유지됩니다.") : text("자료 준비가 완료되지 않았습니다. 실행 진단과 원자료는 보존됩니다."));
        connectedProject->setChanged(true);
        prepareJob.clear(); syncLocks();
    }
    QJsonObject retainedSource() {
        if (importedReference.isEmpty() || draft != baseline.value(text("draft")).toObject()) throw std::runtime_error("Explicitly prepare and save the current applied data before transfer.");
        const auto jobId = importedReference.value(text("job_id")).toString();
        const auto exact = request(documentPath() + text("/result-reference/") + jobId);
        const auto current = request(documentPath());
        const auto raw = request(documentPath() + text("/source-table?start=0&count=1"));
        if (exact.value(text("input_revision")) != current.value(text("input_revision")) || exact.value(text("input_sha256")) != raw.value(text("input_sha256")) || exact.value(text("result_sha256")).toString().isEmpty())
            throw std::runtime_error("The retained result is not the current applied input.");
        importedReference = exact;
        return QJsonObject{{text("document_id"), identifier}, {text("job_id"), jobId}, {text("response"), channel},
            {text("input_revision"), exact.value(text("input_revision"))}, {text("input_sha256"), exact.value(text("input_sha256"))}};
    }
    QProcessEnvironment pythonEnvironment() const {
        auto environment = QProcessEnvironment::systemEnvironment();
        for (const auto* key : {"QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "CAELAB_DATA_TRIAL_REPORT", "CAELAB_DATA_CAPTURE_ONLY"}) environment.remove(text(key));
        const auto sdk = QString::fromUtf8(qgetenv("CAELAB_DONOR_SDK")); QStringList paths;
        for (const auto& path : environment.value(text("PATH")).split(QDir::listSeparator())) {
            bool donorPath = false;
            const auto normalized = QDir::fromNativeSeparators(path);
            for (const auto& prefix : {sdk, QLibraryInfo::path(QLibraryInfo::PrefixPath), QCoreApplication::applicationDirPath()}) {
                const auto normalizedPrefix = QDir::fromNativeSeparators(prefix);
                if (!prefix.isEmpty() && (normalized.compare(normalizedPrefix, Qt::CaseInsensitive) == 0 || normalized.startsWith(normalizedPrefix + QLatin1Char('/'), Qt::CaseInsensitive))) donorPath = true;
            }
            if (!donorPath) paths.append(path);
        }
        environment.insert(text("PATH"), paths.join(QDir::listSeparator()));
        return environment;
    }
    qint64 launchMaterial(const QString& materialId = {}) {
        const auto source = retainedSource();
        const auto context = request(text("/api/workbench/desktop"));
        const auto environment = pythonEnvironment();
        QProcess process; process.setProcessEnvironment(environment); process.setWorkingDirectory(context.value(text("repo_root")).toString());
        process.setProgram(context.value(text("python")).toString());
        QStringList arguments{text("-m"), text("apps.research.desktop"), text("--service"), service, text("material"), text("--observation"), QString::fromUtf8(QJsonDocument(source).toJson(QJsonDocument::Compact))};
        if (!materialId.isEmpty()) arguments << text("--document-id") << materialId;
        process.setArguments(arguments); qint64 pid = 0;
        if (!process.startDetached(&pid)) throw std::runtime_error("The Material process could not be requested. The saved source is preserved.");
        window->statusBar()->showMessage(text("Material window requested. Select a plan and review its test conditions; no fit or adoption has run."));
        return pid;
    }
    void discussSelection() {
        if (!connected() || draft != baseline.value(text("draft")).toObject()) throw std::runtime_error("편집한 열과 단위를 적용한 뒤 논의하세요.");
        const auto context = request(text("/api/workbench/desktop"));
        QJsonObject payload{
            {text("session_id"), baseline.value(text("session_id"))},
            {text("command_id"), QString(text("C") + QUuid::createUuid().toString(QUuid::Id128))}};
        QString endpoint;
        if (importedReference.value(text("job_id")).toString().isEmpty()) {
            payload.insert(text("document_id"), identifier);
            payload.insert(text("expected_generation"), baseline.value(text("generation")));
            endpoint = text("/api/workbench/selection-discussion");
        } else {
            payload.insert(text("source"), retainedSource());
            payload.insert(text("kind"), text("expert"));
            endpoint = text("/api/workbench/data-followup");
        }
        const auto receipt = request(endpoint, &payload);
        if (receipt.value(text("executed")).toBool(true)) throw std::runtime_error("토론 열기에 예상하지 않은 실행 상태가 있습니다.");
        QProcess process; process.setProcessEnvironment(pythonEnvironment());
        process.setWorkingDirectory(context.value(text("repo_root")).toString());
        process.setProgram(context.value(text("python")).toString());
        process.setArguments({text("-m"), text("apps.research.desktop"), text("--service"), service,
            text("expert"), text("--document-id"), receipt.value(text("document")).toObject().value(text("id")).toString()});
        qint64 pid = 0;
        if (!process.startDetached(&pid)) throw std::runtime_error("토론 창을 열지 못했습니다. 선택 자료는 저장되어 있습니다.");
        window->statusBar()->showMessage(text("선택한 자료로 토론을 열었습니다. 질문을 확인하고 보내세요."));
    }
    qint64 launchDataTools(const QString& task) {
        if (!connected() || draft != baseline.value(text("draft")).toObject()) throw std::runtime_error("변경 적용 후 자료 도구를 여세요. 편집 중인 설정은 유지됩니다.");
        const auto current = request(documentPath());
        for (const auto* key : {"session_id", "generation", "input_revision", "draft"})
            if (current.value(text(key)) != baseline.value(text(key))) throw std::runtime_error("원자료를 다시 읽어 현재 입력을 확인한 뒤 자료 도구를 여세요.");
        const auto context = request(text("/api/workbench/desktop"));
        QProcess process; process.setProcessEnvironment(pythonEnvironment()); process.setWorkingDirectory(context.value(text("repo_root")).toString());
        process.setProgram(context.value(text("python")).toString());
        process.setArguments({text("-m"), text("apps.research.desktop"), text("--service"), service, text("data"), text("--pyside"), text("--document-id"), identifier, text("--data-task"), task});
        qint64 pid = 0; if (!process.startDetached(&pid)) throw std::runtime_error("자료 도구 창을 열지 못했습니다. 원자료와 결과는 유지됩니다.");
        window->statusBar()->showMessage(text("같은 자료 문서의 처리와 취득 도구를 열었습니다. 이 창으로 돌아오면 원자료 다시 읽기로 변경을 확인하세요."));
        return pid;
    }
    QJsonObject interactionTrial(const QString& reportPath, bool reopened) {
        if (!reopened) load();
        if (!connected() || !sourceCurve || !sheet || rows.size() != 5) throw std::runtime_error("Interaction check requires its five-row original source.");
        const auto before = request(documentPath());
        auto expect = [](bool condition, const char* message) { if (!condition) throw std::runtime_error(message); };
        auto sorted = [](const QSet<int>& values) { QList<int> ordered = values.values(); std::sort(ordered.begin(), ordered.end()); QJsonArray result; for (int value : ordered) result.append(value); return result; };
        auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
        auto* curveView = dynamic_cast<WorksheetView*>(sourceWorksheet->view());
        window->showNormal(); window->resize(1440, 940);
        if (reopened) {
            expect(channelSpec().value(text("unit")) == text("kPa"), "The saved unit setting did not reopen.");
            expect(channelSpec().value(text("scale")) == 2 && channelSpec().value(text("offset")) == 1, "Scale and offset did not reopen independently.");
            expect(sheet->column(0)->valueAt(0) == 5 && selectedSources == QSet<int>{4}, "Sorted view or original-row selection did not reopen.");
        } else {
            const auto original = draft;
            for (const auto purpose : {"자료 열기", "재료에서 사용"}) {
                QTimer::singleShot(30, this, [] { if (auto* dialog = qobject_cast<QInputDialog*>(QApplication::activeModalWidget())) {
                    dialog->findChild<QComboBox*>()->setCurrentIndex(1); dialog->accept();
                }});
                const QStringList ids{text("first-document"), text("second-document")};
                expect(ids.value(chooseDocument(text(purpose), text("문서"), {text("같은 이름"), text("같은 이름")})) == text("second-document"), "Duplicate titles selected the first document instead of the second ID.");
            }
            // Actual dialog acceptance with no edit must preserve absent/default keys.
            QTimer::singleShot(30, this, [] { if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) dialog->accept(); });
            const int undoStart = connectedProject->undoStack()->index(); editMapping();
            expect(draft == original && connectedProject->undoStack()->index() == undoStart, "Accepting unchanged settings altered the draft or Undo stack.");
            // Cancelled edits remain in the dialog only.
            QTimer::singleShot(30, this, [] { if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) {
                dialog->findChild<QLineEdit*>(QStringLiteral("coreValueUnit"))->setText(QStringLiteral("Pa")); dialog->reject();
            }}); editMapping(); expect(draft == original, "Cancelling settings changed the local draft.");
            // Preserve incomplete numeric text, channel edits and the physical meaning of a new channel.
            CaelabDataSettingsDialog check(draft, rawColumns, channel, window);
            expect(check.findChild<QLineEdit*>(text("coreValueLocation"))->text() == text("재료점") && check.findChild<QLineEdit*>(text("coreValueFrame"))->text() == text("재료 직교좌표"), "Known physical labels were not shown in Korean.");
            expect(check.editedDraft() == draft, "Known translated physical labels changed stored codes without an edit.");
            auto* measures = check.findChild<QComboBox*>(text("coreValueMeasureChoice"));
            measures->setCurrentIndex(measures->findData(text("first_Piola")));
            expect(check.editedDraft().value(text("mapping")).toObject().value(text("columns")).toObject().value(channel).toObject().value(text("measure")) == text("first_Piola"), "A physical choice was saved as a translated label instead of its stored code.");
            auto unknown = draft; auto unknownMapping = unknown.value(text("mapping")).toObject(); auto unknownColumns = unknownMapping.value(text("columns")).toObject(); auto unknownSpec = unknownColumns.value(channel).toObject();
            unknownSpec.insert(text("frame"), text("custom_invalid_frame")); unknownSpec.remove(text("scale")); unknownSpec.remove(text("offset")); unknownColumns.insert(channel, unknownSpec); unknownMapping.insert(text("columns"), unknownColumns); unknown.insert(text("mapping"), unknownMapping);
            CaelabDataSettingsDialog unknownDialog(unknown, rawColumns, channel, window); unknownDialog.focusSection(CaelabDataSettingsDialog::Section::Axis);
            expect(unknownDialog.editedDraft() == unknown, "A context section or unknown physical code changed untouched draft keys.");
            QFocusEvent focusOut(QEvent::FocusOut); QApplication::sendEvent(unknownDialog.findChild<QLineEdit*>(text("coreValueFrame")), &focusOut);
            expect(unknownDialog.editedDraft() == unknown, "Focus-out erased an unknown physical code or inserted scale/offset defaults.");
            check.findChild<QLineEdit*>(text("coreValueScale"))->setText(text("1e"));
            auto* chooser = check.findChild<QComboBox*>(text("coreChannel"));
            chooser->setCurrentIndex(chooser->findText(text("deformation")));
            chooser->setCurrentIndex(chooser->findText(channel));
            expect(check.findChild<QLineEdit*>(text("coreValueScale"))->text() == text("1e"), "Channel switching lost incomplete numeric input.");
            check.findChild<QLineEdit*>(text("coreNewChannel"))->setText(text("새 관측"));
            check.findChild<QPushButton*>(text("coreAddChannel"))->click();
            const auto newSpec = check.editedDraft().value(text("mapping")).toObject().value(text("columns")).toObject().value(text("새 관측")).toObject();
            expect(newSpec.value(text("component")).toString().isEmpty() && newSpec.value(text("measure")).toString().isEmpty(), "A new channel inherited a physical meaning.");
            // The actual accepted dialog becomes exactly one local native Undo command.
            QTimer::singleShot(60, this, [reportPath] { if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) {
                dialog->findChild<QLineEdit*>(QStringLiteral("coreValueUnit"))->setText(QStringLiteral("kPa"));
                dialog->findChild<QLineEdit*>(QStringLiteral("coreValueScale"))->setText(QStringLiteral("2"));
                dialog->findChild<QLineEdit*>(QStringLiteral("coreValueOffset"))->setText(QStringLiteral("1"));
                dialog->grab().save(reportPath + QStringLiteral(".settings.png"));
                dialog->resize(640, 420); QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
                dialog->grab().save(reportPath + QStringLiteral(".settings-narrow.png")); dialog->accept();
            }}); editMapping();
            const auto edited = draft;
            const auto epochBefore = loadEpoch; auto* projectBefore = connectedProject.data();
            QTimer::singleShot(30, this, [] { if (auto* box = qobject_cast<QMessageBox*>(QApplication::activeModalWidget())) box->button(QMessageBox::Cancel)->click(); });
            load(); expect(draft == edited && loadEpoch == epochBefore && connectedProject == projectBefore, "Cancelling Core re-read discarded local edits or Undo identity.");
            expect(connectedProject->undoStack()->index() == undoStart + 1, "One accepted settings dialog did not produce one Undo command.");
            connectedProject->undoStack()->undo(); expect(draft == original, "Native Undo did not restore channel settings.");
            connectedProject->undoStack()->redo(); expect(draft == edited, "Native Redo did not restore channel settings.");
            expect(rawNumber(2, 3) == 2.88 && displayCache->column(2)->valueAt(3) == 2.88, "A unit label or scale setting mutated the raw source view.");
            view->findChild<QTableView*>()->selectRow(1);
            if (selectedSources != QSet<int>{2}) {
                QStringList details; for (int r = 0; r < sheet->rowCount(); ++r) details.append(QString::number(sheet->column(0)->valueAt(r)) + text(":") + QString::number(view->isRowSelected(r)));
                throw std::runtime_error(QString(text("Native spreadsheet selection did not preserve source row 2; connection=") + QString::number(bool(selectionConnection)) + text(" selected=") + QString::fromUtf8(QJsonDocument(sorted(selectedSources)).toJson(QJsonDocument::Compact)) + text(" table=") + details.join(text(","))).toUtf8().constData());
            }
            editSelectedRows(text("quality_rows")); selectSources(QSet<int>{5}); editSelectedRows(text("display_hidden_rows"));
            selectSources(QSet<int>{3}); editSelectedRows(text("exclude_rows"));
            sortRows(2, true);
            expect(sheet->column(0)->valueAt(0) == 5 && rows[0].toInt() == 1, "View sorting changed the original source order.");
        }
        bool guardOpened = false;
        QTimer guardDialog; guardDialog.setInterval(20);
        QObject::connect(&guardDialog, &QTimer::timeout, this, [&] {
            if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) if (dialog->objectName() == text("coreDataSettings")) { guardOpened = true; dialog->grab().save(reportPath + text(".source-editor.png")); dialog->reject(); }
        }); guardDialog.start();
        sourceCurve->setXColumn(sheet->column(1)); sourceCurve->setYColumn(sheet->column(2));
        QApplication::processEvents(); guardDialog.stop();
        expect(guardOpened, "Canonical source editing did not open the actual channel editor.");
        expect(sourceCurve->xColumn() == displayCache->column(1) && sourceCurve->yColumn() == displayCache->column(2), "Native canonical curve source editing bypassed its engineering mapping.");
        const auto selection = channelSpec().value(text("row_selection")).toObject();
        expect(selection.value(text("quality_rows")).toArray() == QJsonArray{2} && selection.value(text("exclude_rows")).toArray() == QJsonArray{3} && selection.value(text("display_hidden_rows")).toArray() == QJsonArray{5}, "Quality, exclusion and hiding were merged.");
        expect(std::isnan(displayCache->column(1)->valueAt(4)) && std::isfinite(displayCache->column(1)->valueAt(2)), "Display hiding was merged with calculation exclusion.");
        sourceWorksheet->dockWidget()->setAsCurrentTab(); sourceWorksheet->setZoomFit(Worksheet::ZoomFit::Fit);
        QApplication::processEvents(QEventLoop::ExcludeUserInputEvents); curveView->fitInView(curveView->scene()->sceneRect(), Qt::KeepAspectRatio);
        QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
        auto hit = [&](double x, double y) {
            bool visible = false; const auto point = sourcePlot->coordinateSystem(sourceCurve->coordinateSystemIndex())->mapLogicalToScene(QPointF(x, y), visible);
            expect(visible, "The native curve test point is outside its axes.");
            QGraphicsSceneMouseEvent press(QEvent::GraphicsSceneMousePress); press.setPos(point); press.setScenePos(sourceCurve->graphicsItem()->mapToScene(point));
            press.setButton(Qt::LeftButton); press.setButtons(Qt::LeftButton);
            expect(curveView->scene()->sendEvent(sourceCurve->graphicsItem(), &press), "The native curve rejected its point press.");
        };
        hit(1, 1.44); expect(selectedSources == QSet<int>({2, 3}), "Duplicate native curve points did not select both original source rows after sorting/hiding.");
        hit(1, 2.88); expect(selectedSources == QSet<int>{4}, "Native curve point selection chose the wrong original row.");
        bool visible = false;
        const auto logical = sourcePlot->coordinateSystem(sourceCurve->coordinateSystemIndex())->mapLogicalToScene(QPointF(1, 1.44), visible);
        const auto pixel = curveView->mapFromScene(sourceCurve->graphicsItem()->mapToScene(logical));
        rangeSelection = true;
        QMouseEvent press(QEvent::MouseButtonPress, QPointF(pixel - QPoint(9, 9)), Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(curveView->viewport(), &press);
        QMouseEvent move(QEvent::MouseMove, QPointF(pixel + QPoint(9, 9)), Qt::NoButton, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(curveView->viewport(), &move);
        QMouseEvent release(QEvent::MouseButtonRelease, QPointF(pixel + QPoint(9, 9)), Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
        QApplication::sendEvent(curveView->viewport(), &release); rangeSelection = false;
        expect(selectedSources == QSet<int>({2, 3}), "Explicit native range selection lost duplicate original rows."); selectSources(QSet<int>{4});
        expect(request(documentPath()) == before, "Opening, selection, settings or local Undo changed Core before Apply.");
        window->grab().save(reportPath + text(".curve.png"));
        window->resize(1024, 768); QApplication::processEvents(QEventLoop::ExcludeUserInputEvents); window->grab().save(reportPath + text(".curve-narrow.png"));
        window->resize(1440, 940); QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
        sheet->dockWidget()->setAsCurrentTab(); QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
        window->grab().save(reportPath + text(".table.png"));
        window->resize(1024, 768); QApplication::processEvents(QEventLoop::ExcludeUserInputEvents); window->grab().save(reportPath + text(".narrow.png"));
        if (!reopened) {
            apply(); expect(baseline.value(text("generation")).toInt() == before.value(text("generation")).toInt() + 1, "Local edits were not applied in exactly one Core update.");
            expect(baseline.value(text("runs")).toArray().isEmpty(), "Local editing or Apply created a numerical result.");
            const auto path = QString::fromUtf8(qgetenv("CAELAB_DATA_VIEW_PATH")); expect(window->save(path), "The interaction view could not save through native Core + view Save.");
        }
        return QJsonObject{{text("status"), text("PASS")}, {text("source_rows"), rows}, {text("selected_rows"), sorted(selectedSources)},
            {text("row_selection"), selection}, {text("document"), request(documentPath())}, {text("data_updates"), reopened ? 0 : 1},
            {text("scope"), reopened ? text("cold reopen preserves original-row selection, view sorting, settings and independent row states") : text("actual native settings dialog, table/point/range selection, duplicate coordinates, sorting/hiding, local Undo, one Apply and atomic Save")}};
    }
    QJsonObject workspaceTrial(const QString& reportPath) {
        load(); const auto before = baseline, original = draft;
        auto settle = [] { QEventLoop loop; QTimer::singleShot(160, &loop, &QEventLoop::quit); loop.exec(QEventLoop::ExcludeUserInputEvents); QApplication::processEvents(QEventLoop::ExcludeUserInputEvents); };
        selectSources(QSet<int>{rows.first().toInt()});
        const auto chosen = selectedSources; const auto chosenChannel = channel;
        auto* view = dynamic_cast<SpreadsheetView*>(sheet->view()); auto* table = view->findChild<QTableView*>();
        QJsonArray headers, values;
        for (int column = 0; column < sheet->columnCount(); ++column) headers.append(QJsonObject{
            {text("logical_column"), column}, {text("native_name"), sheet->column(column)->name()},
            {text("display"), table->model()->headerData(column, Qt::Horizontal, Qt::DisplayRole).toString()},
            {text("tooltip"), table->model()->headerData(column, Qt::Horizontal, Qt::ToolTipRole).toString()}});
        for (int row = 0; row < sheet->rowCount(); ++row) {
            QJsonArray line; for (int column = 0; column <= rawColumns.size(); ++column) line.append(sheet->column(column)->valueAt(row)); values.append(line);
        }
        window->showNormal(); window->resize(1280, 820); QApplication::processEvents(); arrangeAnalysisWorkspace(true);
        tableAction->trigger(); settle(); window->grab().save(reportPath + text(".1280.png"));
        QJsonArray explorerItems, explorerColumns;
        if (auto* tree = window->m_projectExplorer->findChild<QTreeView*>(text("caelabDataExplorerTree"))) {
            for (int column = 0; column < tree->model()->columnCount(); ++column) explorerColumns.append(QJsonObject{{text("column"), column}, {text("hidden"), tree->isColumnHidden(column)}});
            std::function<void(const QModelIndex&)> visit = [&](const QModelIndex& parent) {
                for (int row = 0; row < tree->model()->rowCount(parent); ++row) {
                    const auto index = tree->model()->index(row, 0, parent);
                    explorerItems.append(QJsonObject{{text("name"), index.data().toString()}, {text("type"), index.siblingAtColumn(1).data().toString()}}); visit(index);
                }
            }; visit(QModelIndex());
        }
        const int tableWidth = table->width();
        window->resize(1100, 820); QApplication::processEvents(); tableAction->trigger(); settle();
        window->grab().save(reportPath + text(".1100-table.png"));
        curveAction->trigger(); settle(); window->grab().save(reportPath + text(".1100-curve.png"));
        auto* header = table->horizontalHeader(); const int moved = header->logicalIndex(2);
        header->moveSection(2, header->count() - 1); refreshEngineeringView();
        if (header->visualIndex(moved) != header->count() - 1) throw std::runtime_error("Channel refresh reset a user's view column order.");
        QJsonArray afterMove;
        for (int row = 0; row < sheet->rowCount(); ++row) {
            QJsonArray line; for (int column = 0; column <= rawColumns.size(); ++column) line.append(sheet->column(column)->valueAt(row)); afterMove.append(line);
        }
        if (afterMove != values) throw std::runtime_error("Moving a source header changed logical columns or original values.");
        header->moveSection(header->count() - 1, 2);
        if (selectedSources != chosen || channel != chosenChannel || draft != original || request(documentPath()) != before)
            throw std::runtime_error("Responsive source presentation changed input, channel or original-row selection.");
        // Exercise the existing local command/Undo without submitting anything.
        exclude(); connectedProject->undoStack()->undo();
        if (draft != original || selectedSources != chosen || request(documentPath()) != before)
            throw std::runtime_error("Presentation changed local exclusion Undo or Core input.");
        for (int column = 0; column < sheet->columnCount(); ++column) if (sheet->column(column)->name() != headers[column].toObject().value(text("native_name")).toString())
            throw std::runtime_error("Responsive view activation changed a native source column name.");
        QJsonArray selected; for (int row : chosen) selected.append(row);
        return QJsonObject{{text("status"), text("PASS")}, {text("headers"), headers}, {text("native_values"), values},
            {text("raw_columns"), rawColumns}, {text("document"), before}, {text("selected_rows"), selected},
            {text("channel"), channel}, {text("table_width_at_1280"), tableWidth},
            {text("explorer_items_at_1280"), explorerItems}, {text("explorer_columns_at_1280"), explorerColumns},
            {text("data_updates"), 0}, {text("imports"), 0}, {text("scope"), text("same applied input; compact native headers, responsive table/curve, local exclusion Undo; no save or computation")}};
    }
    QJsonObject unitLayoutTrial(const QString& reportPath, bool reopened) {
        if (!reopened) load();
        if (!connected() || !sheet || !displayCache) throw std::runtime_error("The exact native source is not open.");
        const auto before = request(documentPath()), original = draft;
        auto* table = dynamic_cast<SpreadsheetView*>(sheet->view())->findChild<QTableView*>();
        auto* header = table->horizontalHeader();
        auto values = [this] { QJsonArray rows;
            for (int row = 0; row < sheet->rowCount(); ++row) { QJsonArray line;
                for (int col = 0; col <= rawColumns.size(); ++col) line.append(sheet->column(col)->valueAt(row)); rows.append(line);
            } return rows;
        };
        const auto originalValues = values();
        if (!reopened) selectSources(QSet<int>{rows.first().toInt()});
        const auto chosen = selectedSources;
        if (chosen != QSet<int>{rows.first().toInt()}) throw std::runtime_error("The saved original-row selection was not restored.");
        const auto columns = draft.value(text("mapping")).toObject().value(text("columns")).toObject();
        QJsonObject channels;
        for (auto it = columns.begin(); it != columns.end(); ++it) {
            channel = it.key(); refreshEngineeringView(); showChannelPane(); QJsonArray headers, titles;
            for (int col = 0; col < sheet->columnCount(); ++col) headers.append(QJsonObject{
                {text("display"), table->model()->headerData(col, Qt::Horizontal).toString()},
                {text("tooltip"), table->model()->headerData(col, Qt::Horizontal, Qt::ToolTipRole).toString()}});
            for (auto* axis : sourcePlot->children<Axis>()) titles.append(axis->title()->text().text);
            channels.insert(channel, QJsonObject{{text("headers"), headers}, {text("axis_titles"), titles},
                {text("cache_x_name"), displayCache->column(1)->name()}, {text("cache_y_name"), displayCache->column(2)->name()},
                {text("summary"), channelSummary->text()}});
        }
        channel = before.value(text("draft")).toObject().value(text("mapping")).toObject().value(text("columns")).toObject().contains(text("stress")) ? text("stress") : columns.keys().first();
        refreshEngineeringView(); showChannelPane();
        editSelectedRows(text("exclude_rows")); connectedProject->undoStack()->undo();
        if (draft != original || values() != originalValues || selectedSources != chosen || request(documentPath()) != before)
            throw std::runtime_error("Raw-unit display changed source values, selection, Undo or Core input.");
        int y = -1;
        for (int index = 0; index < rawColumns.size(); ++index) if (rawColumns[index].toObject().value(text("key")) == channelSpec().value(text("column"))) y = index + 1;
        if (!reopened) {
            connectedProject->setChanged(false);
            header->moveSection(header->visualIndex(y), header->count() - 1); header->resizeSection(y, 300);
            if (!connectedProject->isChanged()) throw std::runtime_error("View-only column edits did not mark the native project unsaved.");
        }
        if (header->visualIndex(y) != header->count() - 1 || header->sectionSize(y) != 300)
            throw std::runtime_error("The user's saved visual column order or width was reset.");
        QJsonArray layout;
        for (int col = 0; col < header->count(); ++col) layout.append(QJsonObject{{text("logical_column"), col}, {text("visual_index"), header->visualIndex(col)}, {text("width"), header->sectionSize(col)}});
        if (!reopened && !window->save(QString::fromUtf8(qgetenv("CAELAB_DATA_VIEW_PATH")))) throw std::runtime_error("Native layout Save failed.");
        auto settle = [] { QEventLoop loop; QTimer::singleShot(160, &loop, &QEventLoop::quit); loop.exec(QEventLoop::ExcludeUserInputEvents); };
        window->showNormal(); window->resize(1280, 820); tableAction->trigger(); settle(); window->grab().save(reportPath + text(".1280.png"));
        window->resize(1100, 820); tableAction->trigger(); settle(); window->grab().save(reportPath + text(".1100-table.png"));
        curveAction->trigger(); settle(); window->grab().save(reportPath + text(".1100-curve.png"));
        if (values() != originalValues || selectedSources != chosen || draft != original) throw std::runtime_error("Saving or resizing changed the original input.");
        const auto current = request(documentPath());
        if (reopened && current != before) throw std::runtime_error("Cold layout read issued a Core mutation.");
        return QJsonObject{{text("status"), text("PASS")}, {text("channels"), channels}, {text("layout"), layout},
            {text("native_values"), originalValues}, {text("document"), current}, {text("selected_rows"), QJsonArray{rows.first()}},
            {text("data_updates"), 0}, {text("document_saves"), reopened ? 0 : 1}, {text("scope"), text("raw-unit labels and native visual layout; exact Save then separate-process reopen")}};
    }
    QJsonObject summaryTrial(const QString& reportPath) {
        load(); const auto before = request(documentPath()), original = draft;
        window->showNormal(); window->resize(920, 760); QApplication::processEvents();
        tableAction->trigger(); QApplication::processEvents(); showChannelPane();
        QJsonArray excluded, tableExcluded;
        for (const auto value : rows) if (!rowUsed(value.toInt())) excluded.append(value);
        for (int row = 0; row < sheet->rowCount(); ++row) if (sheet->column(rawColumns.size() + 1)->textAt(row) == text("제외")) tableExcluded.append(static_cast<int>(sheet->column(0)->valueAt(row)));
        const auto initialSummary = channelSummary->text();
        const bool invalid = !before.value(text("diagnostics")).toArray().isEmpty();
        const auto spec = channelSpec();
        const QString scaleText = spec.value(text("scale")).toString(), offsetText = spec.value(text("offset")).toString();
        const bool countMatches = initialSummary.contains(text("계산 제외: ") + QString::number(excluded.size()) + text("행"));
        const bool transformMatches = !invalid || (initialSummary.contains(text("배율: ") + scaleText + text(" (미완성)")) && initialSummary.contains(text("오프셋: ") + offsetText + text(" (미완성)")));
        window->grab().save(reportPath + text(".table.png"));
        curveAction->trigger(); QApplication::processEvents(); showChannelPane();
        int exclusionLines = 0; for (auto* marker : markers) if (dynamic_cast<QGraphicsLineItem*>(marker)) ++exclusionLines;
        const bool maskMatches = excluded == tableExcluded && exclusionLines == 2 * excluded.size();
        window->grab().save(reportPath + text(".curve.png"));
        bool clearUndo = true, invalidPrepareBlocked = true, emptyPreserved = true;
        if (!excluded.isEmpty()) {
            selectSources(QSet<int>{excluded.first().toInt()}); editSelectedRows(text("exclude_rows"), true); showChannelPane();
            clearUndo = rowUsed(excluded.first().toInt()) && channelSummary->text().contains(text("계산 제외: ") + QString::number(excluded.size() - 1) + text("행"));
            connectedProject->undoStack()->undo(); showChannelPane();
            clearUndo = clearUndo && draft == original && channelSummary->text() == initialSummary;
        }
        if (invalid) {
            invalidPrepareBlocked = !prepareAction->isEnabled(); prepareAction->trigger();
            QTimer::singleShot(30, this, [] { if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) {
                dialog->findChild<QLineEdit*>(QStringLiteral("coreValueScale"))->clear();
                dialog->findChild<QLineEdit*>(QStringLiteral("coreValueOffset"))->clear(); dialog->accept();
            }}); editMapping(); showChannelPane();
            emptyPreserved = channelSpec().value(text("scale")) == QJsonValue(text("")) && channelSpec().value(text("offset")) == QJsonValue(text("")) && channelSummary->text().contains(text("빈 값 (미완성)"));
            window->grab().save(reportPath + text(".empty.png"));
            connectedProject->undoStack()->undo(); showChannelPane();
            emptyPreserved = emptyPreserved && draft == original && channelSummary->text() == initialSummary && !prepareAction->isEnabled();
        }
        const bool corePreserved = request(documentPath()) == before;
        window->grab().save(reportPath + text(".restored.png"));
        const bool passed = countMatches && transformMatches && maskMatches && clearUndo && invalidPrepareBlocked && emptyPreserved && corePreserved;
        return QJsonObject{{text("status"), passed ? text("PASS") : text("FAILED")}, {text("summary"), initialSummary}, {text("excluded_source_rows"), excluded}, {text("table_excluded_source_rows"), tableExcluded},
            {text("count_matches"), countMatches}, {text("transform_matches"), transformMatches}, {text("table_curve_mask_matches"), maskMatches}, {text("curve_exclusion_lines"), exclusionLines}, {text("clear_undo_restores"), clearUndo},
            {text("invalid_prepare_blocked"), invalidPrepareBlocked}, {text("empty_and_undo_preserved"), emptyPreserved}, {text("core_preserved"), corePreserved}, {text("document"), before}, {text("data_updates"), 0}, {text("runs"), 0}};
    }
    void workflow(const QString& reportPath, const QString& phase) {
        QJsonObject report;
        try {
            const auto target = QString::fromUtf8(qgetenv("CAELAB_DATA_VIEW_PATH"));
            if (phase == text("unit_layout") || phase == text("unit_layout_reopen")) {
                report = unitLayoutTrial(reportPath, phase == text("unit_layout_reopen"));
            } else if (phase == text("workspace")) {
                report = workspaceTrial(reportPath);
            } else if (phase == text("summary")) {
                report = summaryTrial(reportPath);
            } else if (phase.startsWith(text("tools_"))) {
                load(); const auto before = request(documentPath());
                const auto task = phase.mid(6); const auto pid = launchDataTools(task);
                const auto receiver = QString::fromUtf8(qgetenv("CAELAB_TEST_RECEIPT"));
                QElapsedTimer timer; timer.start();
                while (!QFile::exists(receiver) && timer.elapsed() < 30000) { QEventLoop delay; QTimer::singleShot(40, &delay, &QEventLoop::quit); delay.exec(QEventLoop::ExcludeUserInputEvents); }
                if (!QFile::exists(receiver)) throw std::runtime_error("The actual dedicated Data tool did not confirm its exact document.");
                if (request(documentPath()) != before) throw std::runtime_error("Opening a dedicated Data tool changed Core input or ran an operation.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("task"), task}, {text("pid"), pid}, {text("document"), before}, {text("data_updates"), 0}};
            } else if (phase.startsWith(text("prepare_"))) {
                load(); const auto before = baseline;
                QTimer cancel;
                if (phase == text("prepare_cancel") || phase == text("prepare_later")) {
                    cancel.setInterval(25);
                    QObject::connect(&cancel, &QTimer::timeout, this, [this, reportPath, phase] {
                        if (auto* dialog = window->findChild<QDialog*>(text("caelab-data-prepare"))) {
                            if (phase == text("prepare_later")) { dialog->reject(); return; }
                            if (auto* button = dialog->findChild<QPushButton*>(text("caelab-prepare-cancel"))) { dialog->grab().save(reportPath + text(".progress.png")); button->click(); }
                        }
                    }); cancel.start();
                }
                bool lost = false; QString originalJob;
                try { importData(); } catch (const std::exception&) {
                    if (phase != text("prepare_loss")) throw;
                    lost = true; originalJob = prepareJob;
                    if (originalJob.isEmpty() || !pendingApply.isEmpty()) throw std::runtime_error("A lost status response did not retain the confirmed prepare job.");
                    importData();
                }
                cancel.stop();
                if (phase == text("prepare_later")) { originalJob = prepareJob; if (originalJob.isEmpty()) throw std::runtime_error("Closing progress monitoring erased or cancelled the job."); importData(); if (lastPrepareJob.value(text("cancel_requested")).toBool()) throw std::runtime_error("Closing progress monitoring requested cancellation."); }
                const auto state = lastPrepareJob.value(text("state")).toString();
                if (!prepareJob.isEmpty() || state != (phase == text("prepare_cancel") ? text("CANCELLED") : text("SUCCEEDED"))) throw std::runtime_error("Prepare did not confirm the expected terminal state.");
                if (phase == text("prepare_loss") && (!lost || originalJob != lastPrepareJob.value(text("id")).toString())) throw std::runtime_error("Lost status retry changed the job identity.");
                const auto current = request(documentPath());
                if (current.value(text("generation")) != before.value(text("generation")) || current.value(text("draft")) != before.value(text("draft")) || current.value(text("runs")).toArray().size() != before.value(text("runs")).toArray().size() + 1) throw std::runtime_error("Prepare changed input or submitted duplicate jobs.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("native progress, explicit cancellation or response-loss retry, actual existing JobManager terminal")}, {text("job"), lastPrepareJob}, {text("lost_status_reply"), lost}, {text("document"), current}};
            } else if (phase == text("partial")) {
                load();
                auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
                view->setCellsSelected(1, 0, 1, sheet->columnCount() - 1); exclude(); apply();
                importData(); failNextViewWrite = true;
                if (window->save(target) || pendingXml.isEmpty()) throw std::runtime_error("The native Save hook did not preserve its exact failed view snapshot.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("native Apply, explicit import, Core save acknowledged, injected view failure")},
                    {text("recovery_path"), recoveryPath()}, {text("binding"), pendingBinding}, {text("document"), baseline},
                    {text("view_saved"), false}, {text("data_updates"), 1}};
            } else if (phase == text("retry")) {
                recoverSave(QString::fromUtf8(qgetenv("CAELAB_DATA_RECOVERY_PATH")));
                const auto ack = pendingBinding.value(text("document")).toObject();
                commitView();
                if (fileBinding(target).value(text("document")) != ack) throw std::runtime_error("View retry changed its exact Core acknowledgement.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("new-process recovery and exact view retry; no Core commands")},
                    {text("binding"), fileBinding(target)}, {text("document"), request(documentPath())}, {text("view_saved"), true}, {text("data_updates"), 0}};
            } else if (phase == text("cancel_recovery")) {
                auto* unsaved = new Worksheet(text("Unsaved recovery guard")); window->addAspectToProject(unsaved);
                unsaved->setName(text("Preserve these native edits")); window->project()->setChanged(true);
                auto* owner = window->project(); const auto index = owner->undoStack()->index();
                const auto oldDraft = draft;
                QTimer cancel; cancel.setInterval(20);
                QObject::connect(&cancel, &QTimer::timeout, this, [] {
                    for (auto* widget : QApplication::topLevelWidgets()) {
                        if (!widget->isVisible()) continue;
                        if (auto* box = widget->findChild<QDialogButtonBox*>()) if (auto* button = box->button(QDialogButtonBox::Cancel)) button->click();
                    }
                }); cancel.start();
                bool rejected = false;
                try { recoverSave(QString::fromUtf8(qgetenv("CAELAB_DATA_RECOVERY_PATH"))); } catch (const std::exception&) { rejected = true; }
                cancel.stop();
                if (!rejected || window->project() != owner || owner->undoStack()->index() != index || draft != oldDraft || !owner->isChanged() || unsaved->name() != text("Preserve these native edits"))
                    throw std::runtime_error("Cancelling recovery discarded the current native edits or history.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("real native unsaved-project dialog cancellation preserves Project, edits, draft and Undo")}, {text("data_updates"), 0}};
            } else if (phase == text("offline_save") || phase == text("mismatch_save")) {
                if (!requiresCoreSave() || connected()) throw std::runtime_error("The unverified saved binding was not retained as a protected bound project.");
                QFile original(target); original.open(QIODevice::ReadOnly); const auto bytes = original.readAll(); original.close();
                window->project()->setName(text("Unverified local view edits"));
                if (window->save(target)) throw std::runtime_error("An unverified bound project was saved through the unlinked native path.");
                QFile after(target); after.open(QIODevice::ReadOnly);
                if (after.readAll() != bytes || fileBinding(target).isEmpty() || !window->project()->isChanged()) throw std::runtime_error("The original bound file or unverified local edits were lost.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("unverified bound native view rejects Save and preserves original binding/file and local view edits")}, {text("data_updates"), 0}};
            } else if (phase == text("lost_save")) {
                load(); auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
                view->setCellsSelected(1, 0, 1, sheet->columnCount() - 1); exclude();
                if (window->save(target) || (pendingApply.isEmpty() && !inputConflict)) throw std::runtime_error("The real lost save response did not preserve its pending request or confirmed conflict.");
                const auto requestBefore = pendingApply; const auto draftBefore = draft;
                if ((!inputConflict && window->save(target)) || !inputConflict || !pendingApply.isEmpty() || confirmedReceipt.isEmpty() || conflictJournal.isEmpty() || draft != draftBefore || !mayOpen(QString()))
                    throw std::runtime_error("Confirmed historical save did not enter a recoverable conflict without indefinite locking.");
                QFile journal(conflictJournal); if (!journal.open(QIODevice::ReadOnly)) throw std::runtime_error("The conflict journal is missing.");
                const auto preserved = QJsonDocument::fromJson(journal.readAll()).object();
                if ((!requestBefore.isEmpty() && preserved.value(text("request")) != requestBefore) || preserved.value(text("receipt")) != confirmedReceipt || preserved.value(text("local_draft")) != draft ||
                    confirmedReceipt.value(text("document")).toObject().value(text("dirty")).toBool() || confirmedReceipt.value(text("document")).toObject().value(text("saved_revision")).toString().isEmpty() ||
                    preserved.value(text("request")).toObject().value(text("command_id")) != confirmedReceipt.value(text("command_id")))
                    throw std::runtime_error("The original request, confirmed acknowledgement or local buffer was not preserved.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("real HTTP save reply loss, external input change, same-ID retry, durable acknowledged conflict")},
                    {text("journal"), conflictJournal}, {text("local_draft"), draft}, {text("receipt"), confirmedReceipt}, {text("current_document"), conflictCurrent}, {text("unlocked_for_recovery"), true}};
            } else if (phase == text("conflict_recover")) {
                recoverSave(QString::fromUtf8(qgetenv("CAELAB_DATA_RECOVERY_PATH")));
                if (!inputConflict || !requiresCoreSave() || !pendingApply.isEmpty() || confirmedReceipt.isEmpty()) throw std::runtime_error("The acknowledged conflict could not be reopened safely.");
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("new-process acknowledged conflict recovery preserves local draft and receipt without Core commands")},
                    {text("local_draft"), draft}, {text("receipt"), confirmedReceipt}, {text("data_updates"), 0}};
            } else if (phase == text("reopen")) {
                if (!connected()) throw std::runtime_error("The native saved project did not restore its Core binding.");
                const auto before = request(documentPath());
                const auto source = retainedSource();
                const auto pid = launchMaterial(QString::fromUtf8(qgetenv("CAELAB_MATERIAL_DOCUMENT_ID")));
                const auto receiver = QString::fromUtf8(qgetenv("CAELAB_TEST_RECEIPT"));
                if (!receiver.isEmpty()) {
                    QElapsedTimer timer; timer.start();
                    while (!QFile::exists(receiver) && timer.elapsed() < 30000) {
                        QEventLoop delay; QTimer::singleShot(40, &delay, &QEventLoop::quit); delay.exec(QEventLoop::ExcludeUserInputEvents);
                    }
                    if (!QFile::exists(receiver)) throw std::runtime_error("The actual Material receiver did not confirm the exact observation.");
                }
                if (request(documentPath()) != before) throw std::runtime_error("Reopen or handoff changed the Core Data document.");
                QJsonArray values;
                for (int row = 0; row < sheet->rowCount(); ++row) { QJsonArray data;
                    for (int col = 0; col < rawColumns.size() + 1; ++col) data.append(sheet->column(col)->valueAt(row)); values.append(data);
                }
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("saved native Project cold reopen and exact Material receiver; no Data commands")},
                    {text("source"), source}, {text("material_pid"), pid}, {text("document"), before}, {text("native_values"), values}, {text("data_updates"), 0}};
            } else if (phase == text("file_open")) {
                openSourceFile(QString::fromUtf8(qgetenv("CAELAB_DATA_SOURCE_FILE")), 1);
                if (!connected() || !sourceCurve || !sheet || rawColumns.isEmpty()) throw std::runtime_error("Native source open did not create its linked raw work surface.");
                const auto before = request(documentPath());
                const auto raw = request(documentPath() + text("/source-table?start=0&count=4096"));
                if (raw.value(text("source_rows")) != rows || !before.value(text("runs")).toArray().isEmpty()) throw std::runtime_error("Native source open changed source identities or executed a result.");
                if (QFileInfo(QString::fromUtf8(qgetenv("CAELAB_DATA_SOURCE_FILE"))).suffix().toLower() == text("npz")) {
                    QTimer::singleShot(30, this, [] { if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) {
                        auto* value = dialog->findChild<QComboBox*>(QStringLiteral("coreValueColumn")); value->setCurrentIndex(value->findData(QStringLiteral("stress")));
                        auto* axis = dialog->findChild<QComboBox*>(QStringLiteral("coreAxisColumn")); axis->setCurrentIndex(axis->findData(QStringLiteral("time")));
                        dialog->accept();
                    }}); editMapping();
                    if (!sourceCurve->hasData()) throw std::runtime_error("Named NPZ source mapping did not update the native curve locally.");
                }
                if (request(documentPath()) != before) throw std::runtime_error("Source viewing or named-column mapping changed Core without Apply.");
                QJsonArray nativeColumns;
                for (int column = 0; column < rawColumns.size(); ++column) {
                    QJsonArray values; auto* original = sheet->column(column + 1);
                    for (int row = 0; row < rawColumns[column].toObject().value(text("values")).toArray().size(); ++row)
                        values.append(original->columnMode() == AbstractColumn::ColumnMode::Text ? QJsonValue(original->textAt(row)) : QJsonValue(original->valueAt(row)));
                    nativeColumns.append(QJsonObject{{text("key"), rawColumns[column].toObject().value(text("key"))}, {text("values"), values}});
                }
                report = QJsonObject{{text("status"), text("PASS")}, {text("document"), before}, {text("raw"), raw}, {text("native_columns"), nativeColumns}, {text("scope"), text("native file-open handler uploads through existing Core reader; named NPZ settings remain local; no import")}};
            } else if (phase == text("interaction") || phase == text("interaction_reopen")) {
                report = interactionTrial(reportPath, phase == text("interaction_reopen"));
            } else throw std::runtime_error("Unknown bounded native workflow phase.");
        } catch (const std::exception& error) {
            report = QJsonObject{{text("status"), text("FAILED")}, {text("error"), QString::fromUtf8(error.what())},
                {text("pending_request"), pendingApply}, {text("pending_binding"), pendingBinding}, {text("local_draft"), draft}};
        }
        QSaveFile file(reportPath); if (file.open(QIODevice::WriteOnly)) { file.write(QJsonDocument(report).toJson()); file.commit(); }
        window->grab().save(reportPath + text(".png"));
        // This acceptance exit represents process loss after the recovery journal
        // is committed. It never marks the failed view as saved or deletes it.
        pendingApply = {}; pendingXml.clear(); pendingBinding = {}; if (window->project()) window->project()->setChanged(false);
        QTimer::singleShot(100, qApp, &QApplication::quit);
    }
    void trial(const QString& reportPath) {
        QJsonObject report;
        try {
            window->showNormal(); window->resize(1440, 940); QApplication::processEvents();
            load();
            QApplication::processEvents();
            const auto original = draft;
            const auto generation = baseline.value(text("generation")).toInt();
            auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
            if (!view || rows.size() < 2) throw std::runtime_error("Trial requires at least two original rows.");
            view->setCellsSelected(1, 0, 1, sheet->columnCount() - 1);
            selectSources(QSet<int>{2});
            auto* table = view->findChild<QTableView*>(); auto* header = table->horizontalHeader();
            const QPointF headerPoint(header->sectionViewportPosition(3) + header->sectionSize(3) / 2, header->height() / 2);
            QMouseEvent headerPress(QEvent::MouseButtonPress, headerPoint, header->mapToGlobal(headerPoint.toPoint()), Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
            QMouseEvent headerRelease(QEvent::MouseButtonRelease, headerPoint, header->mapToGlobal(headerPoint.toPoint()), Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
            QApplication::sendEvent(header->viewport(), &headerPress); QApplication::sendEvent(header->viewport(), &headerRelease);
            if (selectedSources != QSet<int>{2} || window->stackedWidget->currentWidget() != channelPane) throw std::runtime_error("Source header selection lost the original row or did not show channel properties.");
            selectSources(QSet<int>{2});
            const bool captureOnly = qEnvironmentVariableIsSet("CAELAB_DATA_CAPTURE_ONLY");
            if (!captureOnly) {
            exclude();
            const auto edited = draft;
            if (edited == original || request(documentPath()).value(text("generation")).toInt() != generation)
                throw std::runtime_error("Local row edit changed Core or did not change its buffer.");
            window->project()->undoStack()->undo();
            if (draft != original) throw std::runtime_error("Native Undo did not restore the local buffer.");
            window->project()->undoStack()->redo();
            if (draft != edited) throw std::runtime_error("Native Redo did not restore the local row edit.");
            apply();
            if (baseline.value(text("generation")).toInt() != generation + 1 || !baseline.value(text("runs")).toArray().isEmpty())
                throw std::runtime_error("Trial did not produce exactly one Data update without execution.");
            if (selectedSources != QSet<int>{2}) throw std::runtime_error("Apply or local Undo changed the selected original row.");
            }
            if (captureOnly) {
                window->showNormal(); window->resize(1440, 940);
                sheet->dockWidget()->setAsCurrentTab();
                QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
                view->setCellsSelected(1, 0, 1, sheet->columnCount() - 1);
                QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
                window->grab().save(reportPath + text(".table.png"));
                if (sourceWorksheet) {
                    sourceWorksheet->dockWidget()->setAsCurrentTab(); sourceWorksheet->setZoomFit(Worksheet::ZoomFit::Fit);
                    QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
                    auto* curveView = dynamic_cast<WorksheetView*>(sourceWorksheet->view());
                    if (curveView) curveView->fitInView(curveView->scene()->sceneRect(), Qt::KeepAspectRatio);
                    QApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
                }
                if (request(documentPath()) != baseline) throw std::runtime_error("Read-only capture changed the Core document.");
            }
            QJsonArray nativeValues;
            for (int row = 0; row < sheet->rowCount(); ++row) {
                QJsonArray values;
                for (int column = 0; column < rawColumns.size() + 1; ++column) values.append(sheet->column(column)->valueAt(row));
                nativeValues.append(values);
            }
            QJsonArray explorerNames;
            if (auto* tree = window->m_projectExplorer->findChild<QTreeView*>(text("caelabDataExplorerTree"))) {
                std::function<void(const QModelIndex&)> collect = [&](const QModelIndex& parent) {
                    for (int row = 0; row < tree->model()->rowCount(parent); ++row) { const auto index = tree->model()->index(row, 0, parent); explorerNames.append(index.data().toString()); collect(index); }
                }; collect(QModelIndex()); tree->expandAll();
            }
            if (!explorerNames.contains(text("원자료")) || !explorerNames.contains(text("응답 곡선"))) throw std::runtime_error((text("The native Explorer lost its source/curve hierarchy: ") + QString::fromUtf8(QJsonDocument(explorerNames).toJson(QJsonDocument::Compact))).toUtf8().constData());
            QApplication::processEvents(); window->grab().save(reportPath + text(".normal.png"));
            const auto chosenChannel = channel; const auto chosenRows = selectedSources;
            window->resize(920, 760); QApplication::processEvents(); tableAction->trigger(); QApplication::processEvents(); window->grab().save(reportPath + text(".narrow-table.png"));
            curveAction->trigger(); QApplication::processEvents(); window->grab().save(reportPath + text(".narrow-curve.png"));
            if (channel != chosenChannel || selectedSources != chosenRows) throw std::runtime_error("Narrow table/curve switching changed the channel or original-row selection.");
            QJsonArray selectedSourceRows; auto orderedSources = selectedSources.values(); std::sort(orderedSources.begin(), orderedSources.end()); for (int source : orderedSources) selectedSourceRows.append(source);
            report = QJsonObject{{text("status"), text("PASS")},
                {text("scope"), captureOnly ? text("read-only native table and curve capture of an externally saved Core document") : text("native source table, row selection, local Undo/Redo, one Core update")},
                {text("data_updates"), captureOnly ? 0 : 1},
                {text("source_rows"), rows}, {text("selected_source_rows"), selectedSourceRows}, {text("native_values"), nativeValues}, {text("explorer_names"), explorerNames}, {text("curve_has_data"), curveHasData}, {text("document"), baseline}};
            QJsonArray propertyChecks;
            auto nativeProperties = [&](AbstractAspect* aspect, const char* expected, const char* capture) {
                const auto undoIndex = window->project()->undoStack()->index();
                const auto undoCount = window->project()->undoStack()->count();
                window->m_projectExplorer->setCurrentAspect(aspect); QApplication::processEvents();
                auto* properties = window->stackedWidget->currentWidget();
                if (!properties || properties == channelPane || !properties->inherits(expected)) throw std::runtime_error("Selecting a graph or independent native object lost its native properties editor.");
                auto serialized = [aspect] { QByteArray xml; QXmlStreamWriter writer(&xml); aspect->save(&writer); return xml; };
                const auto values = serialized();
                CaelabDataProperties::prepare(properties); CaelabDataProperties::prepare(properties);
                if (window->stackedWidget->currentWidget() != properties || serialized() != values || window->project()->undoStack()->index() != undoIndex || window->project()->undoStack()->count() != undoCount) throw std::runtime_error("Preparing native properties changed its editor, saved values or Undo stack.");
                window->resize(1440, 940); QApplication::processEvents(); window->grab().save(reportPath + text(capture) + text(".normal.png"));
                window->resize(920, 760); QApplication::processEvents(); window->grab().save(reportPath + text(capture));
                if (window->stackedWidget->currentWidget() != properties || window->m_projectExplorer->currentAspect() != aspect) throw std::runtime_error("Responsive docking replaced an explicitly selected native editor.");
                auto* scroll = properties->findChild<QScrollArea*>(text("caelabNativePropertiesScroll"));
                // MainWin also owns the original scroll area around stackedWidget.
                // Depending on the other native editors' size hints, it can own
                // horizontal overflow instead of the adapter's inner scroll area.
                for (auto* parent = properties->parentWidget(); parent && (!scroll || scroll->horizontalScrollBar()->maximum() <= 0); parent = parent->parentWidget())
                    if (auto* ancestor = qobject_cast<QScrollArea*>(parent); ancestor && ancestor->horizontalScrollBar()->maximum() > 0) scroll = ancestor;
                if (!scroll || scroll->horizontalScrollBar()->maximum() <= 0) throw std::runtime_error("Narrow native properties have no horizontal path to their controls.");
                scroll->horizontalScrollBar()->setValue(scroll->horizontalScrollBar()->maximum()); QApplication::processEvents(); window->grab().save(reportPath + text(capture) + text(".right.png"));
                scroll->horizontalScrollBar()->setValue(0);
                const auto originalName = aspect->name();
                QLineEdit* nameField = nullptr;
                for (auto* candidate : properties->findChildren<QLineEdit*>(text("leName")))
                    if (candidate->isVisibleTo(properties) && candidate->text() == originalName) { nameField = candidate; break; }
                const auto originalValues = serialized();
                const auto editIndex = window->project()->undoStack()->index();
                if (!nameField || nameField->text() != originalName) throw std::runtime_error("The native name editor lost the selected object's original name.");
                nameField->setText(originalName + text(" 이름 편집 확인"));
                const bool invoked = QMetaObject::invokeMethod(nameField, "textEdited", Qt::DirectConnection);
                if (!invoked || aspect->name() == originalName || window->project()->undoStack()->index() != editIndex + 1) throw std::runtime_error((text("Native edit diagnostic: ") + text(expected) + text(" field=") + QString::fromLatin1(nameField->metaObject()->className()) + text(" text=") + nameField->text() + text(" aspect=") + aspect->name() + text(" invoked=") + QString::number(invoked) + text(" undo=") + QString::number(editIndex) + text("->") + QString::number(window->project()->undoStack()->index()) + text(" aspectAware=") + QString::number(aspect->isUndoAware()) + text(" projectAware=") + QString::number(window->project()->isUndoAware())).toUtf8().constData());
                window->project()->undoStack()->undo();
                if (aspect->name() != originalName || serialized() != originalValues || nameField->text() != originalName || window->project()->undoStack()->index() != editIndex) throw std::runtime_error("Native Undo did not restore the original name and values through the wrapped editor.");
                if (channel != chosenChannel || selectedSources != chosenRows || draft != baseline.value(text("draft")).toObject()) throw std::runtime_error("Native property selection changed the source channel, original rows or Core draft.");
                propertyChecks.append(QJsonObject{{text("editor"), text(expected)}, {text("values_and_undo_preserved"), true}, {text("same_native_editor"), true}, {text("native_name_edit_and_undo"), true}, {text("horizontal_range"), scroll->horizontalScrollBar()->maximum()}, {text("scroll_viewport_width"), scroll->viewport()->width()}, {text("scroll_content_width"), scroll->widget()->width()}});
            };
            nativeProperties(sourcePlot->children<Axis>().first(), "AxisDock", ".axis-properties.png");
            nativeProperties(sourceCurve, "XYCurveDock", ".line-properties.png");
            auto* independent = new Worksheet(text("독립 그래프 확인"));
            auto* independentPlot = new CartesianPlot(text("자유 곡선")); independent->addChild(independentPlot); independentPlot->setType(CartesianPlot::Type::TwoAxes);
            auto* independentCurve = new XYCurve(text("독립 곡선")); independentPlot->addChild(independentCurve);
            independentCurve->setXColumn(sheet->column(1)); independentCurve->setYColumn(sheet->column(2));
            auto* legend = new CartesianPlotLegend(text("범례")); independentPlot->addLegend(legend);
            window->addAspectToProject(independent);
            nativeProperties(independent, "WorksheetDock", ".independent-properties.png");
            nativeProperties(legend, "CartesianPlotLegendDock", ".legend-properties.png");
            if (independentCurve->xColumn() != sheet->column(1) || independentCurve->yColumn() != sheet->column(2) || sourceEditQueued) throw std::runtime_error("Independent native curve editing was routed through the canonical channel guard.");
            window->m_projectExplorer->setCurrentAspect(sheet); selectSources(chosenRows); showChannelPane();
            report.insert(text("native_properties_preserved"), true);
            report.insert(text("native_property_checks"), propertyChecks);
        } catch (const std::exception& error) {
            report = QJsonObject{{text("status"), text("FAILED")}, {text("error"), QString::fromUtf8(error.what())},
                {text("pending_request"), pendingApply}, {text("local_draft"), draft}, {text("baseline"), baseline}};
        }
        QSaveFile file(reportPath);
        if (file.open(QIODevice::WriteOnly)) { file.write(QJsonDocument(report).toJson()); file.commit(); }
        window->grab().save(reportPath + text(".png"));
        if (window->project()) window->project()->setChanged(false);
        QTimer::singleShot(100, qApp, &QApplication::quit);
    }
public:
    ~CaelabDataBridge() override { releaseActivation(); }
    static CaelabDataBridge* from(MainWin* host) {
        for (auto* child : host->children()) if (auto* bridge = dynamic_cast<CaelabDataBridge*>(child)) return bridge;
        return nullptr;
    }
    bool connected() const { return connectedProject && connectedProject == window->project(); }
    bool requiresCoreSave() const { return boundProject && boundProject == window->project(); }
    void finishedOpen() { openingLease.reset(); openingPath.clear(); openingBinding = {}; openingDocument = {}; }
    bool openWasForwarded() const { return openingForwarded; }
    bool mayOpen(const QString& path) {
        finishedOpen(); openingForwarded = false;
        if (!pendingApply.isEmpty() || pendingView() || !prepareJob.isEmpty()) {
            window->statusBar()->showMessage(text("Finish the pending exact save or command before switching documents.")); return false;
        }
        try {
            const auto binding = fileBinding(path);
            if (binding.isEmpty()) return true;
            const auto acknowledgement = binding.value(text("document")).toObject();
            const auto target = acknowledgement.value(text("id")).toString();
            const auto targetService = service.isEmpty() ? binding.value(text("service_url")).toString() : service;
            const auto current = request(text("/api/workbench/documents/") + target, nullptr, targetService);
            if (current.value(text("input_revision")) != acknowledgement.value(text("input_revision")) || current.value(text("draft")) != acknowledgement.value(text("draft")))
                throw std::runtime_error("The saved native view refers to an older Core input. Its file is preserved; reopen the matching Core revision explicitly.");
            auto lease = prepareActivation(current, target, targetService);
            if (lease->forwarded) { openingForwarded = true; return false; }
            openingPath = QFileInfo(path).absoluteFilePath(); openingBinding = binding; openingDocument = current; openingLease = std::move(lease);
        } catch (const std::exception& error) { window->statusBar()->showMessage(QString::fromUtf8(error.what())); return false; }
        return true;
    }
    void opened(const QString& path) {
        guarded([this, path] { restoreBinding(path); });
        const auto phase = QString::fromUtf8(qgetenv("CAELAB_DATA_WORKFLOW_PHASE"));
        if ((phase == text("reopen") || phase == text("offline_save") || phase == text("mismatch_save") || phase == text("interaction_reopen")) && !workflowStarted) {
            workflowStarted = true;
            const auto report = QString::fromUtf8(qgetenv("CAELAB_DATA_TRIAL_REPORT"));
            QTimer::singleShot(0, this, [this, report, phase] { workflow(report, phase); });
        }
    }
    bool saveConnected(const QString& path) {
        try { beginSave(path); const bool fail = failNextViewWrite; failNextViewWrite = false; return commitView(fail); }
        catch (const std::exception& error) {
            if (connected()) connectedProject->setChanged(true);
            syncLocks(); window->statusBar()->showMessage(QString::fromUtf8(error.what())); return false;
        }
    }
    explicit CaelabDataBridge(MainWin* host) : QObject(host), window(host), network(this),
        service(QString::fromUtf8(qgetenv("CAELAB_SERVICE_URL"))), identifier(QString::fromUtf8(qgetenv("CAELAB_DATA_DOCUMENT_ID"))) {
        QObject::connect(qApp, &QCoreApplication::aboutToQuit, this, [this] { releaseActivation(); });
        const QMap<QString, QString> captions{{text("File"), text("파일")}, {text("Edit"), text("편집")}, {text("View"), text("보기")},
            {text("Spreadsheet"), text("표")}, {text("Matrix"), text("행렬")}, {text("Worksheet"), text("그래프")}, {text("Data Extractor"), text("자료 추출")},
            {text("Windows"), text("창")}, {text("Tools"), text("도구")}, {text("Settings"), text("설정")}, {text("Help"), text("도움말")}};
        for (auto* action : window->menuBar()->actions()) {
            auto label = action->text(); label.remove(QLatin1Char('&'));
            if (captions.contains(label)) action->setText(captions.value(label));
        }
        for (const auto& item : QList<QPair<QString, QString>>{{text("file_new"), text("새 작업")}, {text("file_open"), text("저장된 작업 열기…")},
            {text("file_save_as"), text("다른 이름으로 저장…")}, {text("edit_redo"), text("다시 실행")}})
            if (auto* action = window->actionCollection()->action(item.first)) action->setText(item.second);
        window->m_projectExplorerDock->setWindowTitle(text("자료 탐색기"));
        menu = window->menuBar()->addMenu(text("자료"));
        auto* sourceFile = menu->addAction(text("원자료 열기…"));
        auto* coreFile = menu->addAction(text("자료 문서 열기…"));
        readAction = menu->addAction(text("원자료 다시 읽기"));
        menu->addSeparator();
        auto* settings = settingsAction = menu->addAction(text("열과 단위…"));
        auto* sorted = menu->addAction(text("표 정렬…"));
        auto* range = menu->addAction(text("곡선 범위 선택")); range->setCheckable(true);
        excludeAction = menu->addAction(text("선택 행 계산 제외"));
        auto* included = menu->addAction(text("선택 행 계산 포함"));
        auto* quality = menu->addAction(text("선택 행 품질 표시"));
        auto* clearQuality = menu->addAction(text("선택 행 품질 표시 해제"));
        auto* hidden = menu->addAction(text("선택 행 숨기기"));
        auto* showAll = menu->addAction(text("숨긴 행 모두 표시"));
        menu->addSeparator();
        auto* applied = applyAction = menu->addAction(text("변경 적용"));
        auto* saved = saveAction = window->actionCollection()->action(text("file_save"));
        saved->setText(text("자료 저장")); menu->addAction(saved);
        auto* retry = retryAction = menu->addAction(text("다시 시도"));
        auto* recovery = menu->addAction(text("중단된 작업 복구…"));
        auto* prepared = prepareAction = menu->addAction(text("자료 준비"));
        auto* material = materialAction = menu->addAction(text("재료에서 사용…"));
        discussAction = menu->addAction(text("선택 대상으로 논의…"));
        QObject::connect(discussAction, &QAction::triggered, this, [this] { guarded([this] { discussSelection(); }); });
        menu->addSeparator();
        auto* processing = menu->addAction(text("자료 처리…"));
        auto* acquisition = menu->addAction(text("자료 취득…"));
        documentActions = {sourceFile, coreFile, recovery};
        menu->addSeparator();
        tableAction = menu->addAction(text("원표 보기")); curveAction = menu->addAction(text("곡선 보기"));
        channelPane = new QWidget(window->stackedWidget); channelPane->setObjectName(text("caelab-channel-properties")); channelPane->setMinimumWidth(220);
        auto* channelLayout = new QVBoxLayout(channelPane);
        auto* heading = new QLabel(text("선택 채널"), channelPane); channelLayout->addWidget(heading);
        channelChoices = new QComboBox(channelPane); channelChoices->setAccessibleName(text("선택 채널"));
        channelChoices->setMinimumContentsLength(12); channelChoices->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
        channelChoices->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Fixed); channelLayout->addWidget(channelChoices);
        channelSummary = new QLabel(channelPane); channelSummary->setWordWrap(true); channelLayout->addWidget(channelSummary);
        auto* editChannel = new QToolButton(channelPane); editChannel->setDefaultAction(settings); editChannel->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); channelLayout->addWidget(editChannel);
        QObject::connect(editChannel, &QToolButton::pressed, this, [this] { nextMappingSection = sourceColumnSection; });
        channelLayout->addStretch(); window->stackedWidget->addWidget(channelPane);
        QObject::connect(channelChoices, &QComboBox::currentIndexChanged, this, [this](int index) {
            if (updatingChannelPane || index < 0) return;
            channel = channelChoices->itemData(index).toString(); refreshEngineeringView(); showChannelPane();
        });
        QObject::connect(window->m_projectExplorer, &ProjectExplorer::selectedAspectsChanged, this, [this](const QList<AbstractAspect*>& aspects) {
            if (!connected() || aspects.size() != 1 || !sheet) return;
            if (aspects.first() == sheet || aspects.first() == sourceWorksheet) { showChannelPane(); return; }
            for (int index = 1; index <= rawColumns.size(); ++index) if (aspects.first() == sheet->column(index)) { selectSourceColumn(index); return; }
            // GuiObserver has already selected the original native editor. Keep its
            // identity and editing behavior while making captions and controls reachable.
            auto* properties = window->stackedWidget->currentWidget();
            if (!properties || properties == channelPane) return;
            if (properties->inherits("AxisDock") || properties->inherits("XYCurveDock") || properties->inherits("CartesianPlotLegendDock") || properties->inherits("WorksheetDock")) {
                CaelabDataProperties::prepare(properties);
                window->m_propertiesDock->setWindowTitle(properties->windowTitle());
            }
        });
        QObject::connect(tableAction, &QAction::triggered, this, [this] { if (sheet) { const auto chosen = selectedSources; sheet->dockWidget()->setAsCurrentTab(); window->activateSubWindowForAspect(sheet); selectSources(chosen); showChannelPane(); refreshExplorerNames(); } });
        QObject::connect(curveAction, &QAction::triggered, this, [this] { if (sourceWorksheet) { const auto chosen = selectedSources; sourceWorksheet->dockWidget()->setAsCurrentTab(); window->activateSubWindowForAspect(sourceWorksheet); selectSources(chosen); showChannelPane(); refreshExplorerNames(); } });
        sourceFile->setShortcut(QKeySequence(text("Ctrl+Shift+O"))); settings->setShortcut(QKeySequence(text("Ctrl+M")));
        excludeAction->setShortcut(QKeySequence(text("Ctrl+E"))); applied->setShortcut(QKeySequence(text("Ctrl+Return")));
        prepared->setShortcut(QKeySequence(text("Ctrl+Shift+P"))); material->setShortcut(QKeySequence(text("Ctrl+Shift+M")));
        tableAction->setShortcut(QKeySequence(text("Alt+1"))); curveAction->setShortcut(QKeySequence(text("Alt+2")));
        sourceFile->setIcon(window->style()->standardIcon(QStyle::SP_DialogOpenButton));
        settings->setIcon(window->style()->standardIcon(QStyle::SP_FileDialogDetailedView));
        applied->setIcon(window->style()->standardIcon(QStyle::SP_DialogApplyButton));
        prepared->setIcon(window->style()->standardIcon(QStyle::SP_MediaPlay));
        material->setIcon(window->style()->standardIcon(QStyle::SP_ArrowForward));
        auto* tools = new QToolBar(text("자료 작업"), window); tools->setObjectName(text("caelab-data-workspace"));
        tools->setToolButtonStyle(Qt::ToolButtonTextBesideIcon); tools->setIconSize(QSize(16, 16)); window->addToolBar(tools);
        tools->addActions({sourceFile, saved});
        if (auto* undo = window->actionCollection()->action(text("edit_undo"))) { undo->setText(text("실행 취소")); menu->addAction(undo); tools->addAction(undo); }
        tools->addSeparator(); tools->addActions({settings, excludeAction, applied, prepared, material});
        tools->addSeparator(); tools->addActions({tableAction, curveAction});
        editActions = {settings, sorted, range, included, quality, clearQuality, hidden, showAll, processing, acquisition};
        QObject::connect(sourceFile, &QAction::triggered, this, [this] { guarded([this] { openSourceFile(); }); });
        QObject::connect(coreFile, &QAction::triggered, this, [this] { guarded([this] { openCoreData(); }); });
        QObject::connect(settings, &QAction::triggered, this, [this] { const auto section = nextMappingSection; nextMappingSection = CaelabDataSettingsDialog::Section::All; guarded([this, section] { editMapping(section); }); });
        QObject::connect(sorted, &QAction::triggered, this, [this] { guarded([this] {
            QStringList columns{text("원행")}; for (const auto item : rawColumns) columns.append(item.toObject().value(text("name")).toString());
            bool accepted = false; const auto selected = QInputDialog::getItem(window, text("표 정렬"), text("정렬 열"), columns, 0, false, &accepted); if (!accepted) return;
            const auto order = QInputDialog::getItem(window, text("표 정렬"), text("방향"), {text("오름차순"), text("내림차순")}, 0, false, &accepted); if (accepted) sortRows(columns.indexOf(selected) - 1, order == text("내림차순"));
        }); });
        QObject::connect(range, &QAction::toggled, this, [this](bool enabled) { rangeSelection = enabled; if (!enabled && rubberBand) rubberBand->hide(); });
        QObject::connect(included, &QAction::triggered, this, [this] { guarded([this] { editSelectedRows(text("exclude_rows"), true); }); });
        QObject::connect(quality, &QAction::triggered, this, [this] { guarded([this] { editSelectedRows(text("quality_rows")); }); });
        QObject::connect(clearQuality, &QAction::triggered, this, [this] { guarded([this] { editSelectedRows(text("quality_rows"), true); }); });
        QObject::connect(hidden, &QAction::triggered, this, [this] { guarded([this] { editSelectedRows(text("display_hidden_rows")); }); });
        QObject::connect(showAll, &QAction::triggered, this, [this] { guarded([this] { editSelectedRows(text("display_hidden_rows"), true, true); }); });
        QObject::connect(readAction, &QAction::triggered, this, [this] { guarded([this] { load(); }); });
        QObject::connect(excludeAction, &QAction::triggered, this, [this] { guarded([this] { editSelectedRows(text("exclude_rows")); }); });
        QObject::connect(applied, &QAction::triggered, this, [this] { guarded([this] { apply(); }); });
        QObject::connect(retry, &QAction::triggered, this, [this] { guarded([this] {
            const auto operation = pendingApply.value(text("operation")).toString();
            if (!prepareJob.isEmpty()) importData();
            else if (operation == text("data.update")) apply();
            else if (operation == text("data.import")) importData();
            else { if (pendingXml.isEmpty()) beginSave(pendingPath); commitView(); }
        }); });
        QObject::connect(recovery, &QAction::triggered, this, [this] {
            const auto path = QFileDialog::getOpenFileName(window, text("중단된 작업 복구"), QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + text("/caelab-data-recovery"), text("복구 기록 (*.json)"));
            if (!path.isEmpty()) guarded([this, path] { recoverSave(path); });
        });
        QObject::connect(prepared, &QAction::triggered, this, [this] { guarded([this] { importData(); }); });
        QObject::connect(processing, &QAction::triggered, this, [this] { guarded([this] { launchDataTools(text("processing")); }); });
        QObject::connect(acquisition, &QAction::triggered, this, [this] { guarded([this] { launchDataTools(text("acquisition")); }); });
        QObject::connect(material, &QAction::triggered, this, [this] { guarded([this] {
            if (!pendingXml.isEmpty() || !pendingApply.isEmpty()) throw std::runtime_error("Finish the pending save or command first.");
            if (!connected()) throw std::runtime_error("먼저 자료 문서를 여세요.");
            QString path = connectedProject->fileName();
            if (path.isEmpty()) path = QFileDialog::getSaveFileName(window, text("자료 저장"), QString(), text("자료 작업 (*.lml)"));
            if (path.isEmpty()) return;
            beginSave(path); if (!commitView()) return;
            const auto documents = request(text("/api/workbench/documents")).value(text("documents")).toArray();
            QStringList labels{text("새 재료…")}, identifiers{QString()};
            for (const auto item : documents) { const auto doc = item.toObject();
                if (doc.value(text("kind")) == text("material") && doc.value(text("draft")).toObject().value(text("backend")) == text("material.felupe")) {
                    labels.append(doc.value(text("title")).toString()); identifiers.append(doc.value(text("id")).toString());
                }
            }
            const int choice = chooseDocument(text("재료에서 사용"), text("관측 자료를 검토할 재료"), labels);
            if (choice >= 0 && choice < identifiers.size()) launchMaterial(identifiers.value(choice));
        }); });
        window->installEventFilter(this);
        if (window->project() && !window->project()->fileName().isEmpty()) guarded([this] { restoreBinding(window->project()->fileName(), true); });
        const auto report = QString::fromUtf8(qgetenv("CAELAB_DATA_TRIAL_REPORT"));
        const auto phase = QString::fromUtf8(qgetenv("CAELAB_DATA_WORKFLOW_PHASE"));
        const bool afterOpen = phase == text("reopen") || phase == text("offline_save") || phase == text("mismatch_save") || phase == text("interaction_reopen");
        if (!report.isEmpty() && !afterOpen) QTimer::singleShot(300, this, [this, report, phase] { if (phase.isEmpty()) trial(report); else workflow(report, phase); });
        if (!report.isEmpty() && afterOpen) QTimer::singleShot(15000, this, [this, report, phase] { if (!workflowStarted) { workflowStarted = true; workflow(report, phase); } });
        if (report.isEmpty() && !identifier.isEmpty() && QCoreApplication::arguments().size() == 1)
            QTimer::singleShot(0, this, [this] { guarded([this] { load(); }); });
        syncLocks();
    }
};
