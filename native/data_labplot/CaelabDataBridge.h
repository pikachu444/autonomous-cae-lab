// SPDX-FileCopyrightText: 2026 Autonomous CAE Lab contributors
// SPDX-License-Identifier: GPL-2.0-or-later
// Bounded donor trial. This is not the production Data editor or save adapter.
#pragma once
#include "MainWin.h"
#include "backend/core/Project.h"
#include "backend/core/column/Column.h"
#include "backend/lib/UndoStack.h"
#include "backend/spreadsheet/Spreadsheet.h"
#include "backend/worksheet/Worksheet.h"
#include "backend/worksheet/TextLabel.h"
#include "backend/worksheet/plots/cartesian/Axis.h"
#include "backend/worksheet/plots/cartesian/CartesianPlot.h"
#include "backend/worksheet/plots/cartesian/XYCurve.h"
#include "frontend/spreadsheet/SpreadsheetView.h"
#include "frontend/core/ContentDockWidget.h"
#include "frontend/worksheet/WorksheetView.h"
#include <QEventLoop>
#include <QInputDialog>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMenuBar>
#include <QNetworkAccessManager>
#include <QNetworkReply>
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
#include <stdexcept>
#include <limits>
#include <functional>

class CaelabDataBridge : public QObject {
    static QString text(const char* value) { return QString::fromUtf8(value); }
    MainWin* window;
    QNetworkAccessManager network;
    QPointer<Spreadsheet> sheet;
    QPointer<Worksheet> sourceWorksheet;
    QPointer<Project> connectedProject;
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
    QList<QPair<QPointer<QAction>, bool>> lockedActions;
    int loadEpoch{0};
    bool curveHasData{false};
    bool busy{false};
    bool workflowStarted{false};
    bool failNextViewWrite{false};
    bool pendingView() const { return !pendingXml.isEmpty() || !pendingBinding.isEmpty(); }

    QJsonObject request(const QString& path, const QJsonObject* body = nullptr) {
        QNetworkRequest query{QUrl(service + path)};
        query.setTransferTimeout(30000);
        if (body) {
            const auto overview = request(text("/api/overview"));
            query.setRawHeader(QByteArrayLiteral("X-CAE-Token"), overview.value(text("token")).toString().toUtf8());
            query.setHeader(QNetworkRequest::ContentTypeHeader, text("application/json"));
        }
        auto* reply = body ? network.post(query, QJsonDocument(*body).toJson(QJsonDocument::Compact)) : network.get(query);
        QEventLoop loop;
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        loop.exec(QEventLoop::ExcludeUserInputEvents);
        const auto bytes = reply->readAll();
        const auto error = reply->error();
        reply->deleteLater();
        const auto result = QJsonDocument::fromJson(bytes).object();
        if (error != QNetworkReply::NoError || result.isEmpty())
            throw std::runtime_error(bytes.constData());
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
        if ((!pendingApply.isEmpty() || pendingView()) && lockedActions.isEmpty()) {
            for (auto* action : window->findChildren<QAction*>()) {
                if (action->parent() == menu || action == menu->menuAction()) continue;
                lockedActions.append({action, action->isEnabled()}); action->setEnabled(false);
                QObject::connect(action, &QAction::changed, this, [this, action] {
                    if ((!pendingApply.isEmpty() || pendingView()) && action->isEnabled()) action->setEnabled(false);
                });
            }
        } else if (pendingApply.isEmpty() && !pendingView() && !lockedActions.isEmpty()) {
            const auto restore = lockedActions; lockedActions.clear();
            for (const auto& entry : restore) if (entry.first) entry.first->setEnabled(entry.second);
        }
        readAction->setEnabled(pendingApply.isEmpty() && !pendingView()); excludeAction->setEnabled(pendingApply.isEmpty() && !pendingView());
    }
    bool eventFilter(QObject* watched, QEvent* event) override {
        if (watched == window && event->type() == QEvent::Close && (!pendingApply.isEmpty() || pendingView())) {
            static_cast<QCloseEvent*>(event)->ignore();
            window->statusBar()->showMessage(text("Retry the pending Core command or exact view save before closing. The buffer is preserved."));
            return true;
        }
        return QObject::eventFilter(watched, event);
    }
    class DraftChange : public QUndoCommand {
        QPointer<CaelabDataBridge> bridge;
        QJsonObject before, after;
        int epoch;
    public:
        DraftChange(CaelabDataBridge* owner, const QJsonObject& value)
            : QUndoCommand(CaelabDataBridge::text("Data calculation selection")), bridge(owner), before(owner->draft), after(value), epoch(owner->loadEpoch) {}
        void undo() override { if (bridge && bridge->connected() && bridge->loadEpoch == epoch && bridge->pendingApply.isEmpty() && !bridge->pendingView()) { bridge->draft = before; bridge->connectedProject->setChanged(true); } }
        void redo() override { if (bridge && bridge->connected() && bridge->loadEpoch == epoch && bridge->pendingApply.isEmpty() && !bridge->pendingView()) { bridge->draft = after; bridge->connectedProject->setChanged(true); } }
    };
    void load() {
        if (!pendingApply.isEmpty() || pendingView()) throw std::runtime_error("Complete the pending command or exact view save before reading another Core input.");
        if (connected() && draft != baseline.value(text("draft")).toObject() &&
            QMessageBox::question(window, text("Unapplied Data edits"), text("Discard local Data edits and read Core again?"), QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Discard) return;
        if (service.isEmpty() || identifier.isEmpty())
            throw std::runtime_error("Set CAELAB_SERVICE_URL and CAELAB_DATA_DOCUMENT_ID for the bounded donor trial.");
        baseline = request(documentPath()); draft = baseline.value(text("draft")).toObject(); ++loadEpoch;
        importedReference = {}; savedAck = {};
        attachProject();
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
        auto* created = new Spreadsheet(text("Core source"));
        created->setColumnCount(columns.size() + 1); created->setRowCount(rows.size());
        QVector<double> sourceRows;
        for (const auto row : rows) sourceRows.append(row.toDouble());
        created->column(0)->setName(text("Source row")); created->column(0)->setValues(sourceRows);
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
        if (x >= 0 && y >= 0) {
            auto* worksheet = new Worksheet(text("Core curve")); sourceWorksheet = worksheet;
            auto* plot = new CartesianPlot(text("Source values"));
            worksheet->addChild(plot); plot->setType(CartesianPlot::Type::TwoAxes);
            worksheet->setPageRect(QRectF(0, 0, 2100, 1400));
            plot->setRect(QRectF(150, 100, 1800, 1120));
            plot->setHorizontalPadding(240); plot->setVerticalPadding(180);
            plot->title()->setText(TextLabel::TextWrapper(text("Original source response")));
            const auto axisSpec = spec.value(text("axis")).toObject();
            const QString xLabel = axisSpec.value(text("name")).toString() + text(" (") + axisSpec.value(text("unit")).toString() + text(")");
            const QString yLabel = text("Stress (") + spec.value(text("unit")).toString() + text(")");
            for (auto* axis : plot->children<Axis>())
                axis->title()->setText(TextLabel::TextWrapper(axis->orientation() == WorksheetElement::Orientation::Horizontal ? xLabel : yLabel));
            auto* curve = new XYCurve(channel); plot->addChild(curve);
            curve->setXColumn(created->column(x)); curve->setYColumn(created->column(y));
            window->addAspectToProject(worksheet);
            worksheet->setZoomFit(Worksheet::ZoomFit::Fit);
            curveHasData = curve->hasData();
        }
        window->statusBar()->showMessage(text("Core source loaded in a temporary donor project. Native Save stores a LabPlot view only; Core save is not connected."));
    }
    void exclude() {
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
    QJsonObject command(const QString& operation, const QJsonObject& arguments = {}) {
        if (!connected()) throw std::runtime_error("This native project is not connected to a Core Data document.");
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
        const auto acknowledged = receipt.value(text("document")).toObject();
        const auto current = request(documentPath());
        for (const auto* key : {"session_id", "generation", "input_revision", "draft"})
            if (current.value(text(key)) != acknowledged.value(text(key)))
                throw std::runtime_error("Apply is acknowledged but Core has since changed. Keep the local buffer and recover explicitly.");
        baseline = current; pendingApply = {};
        syncLocks();
        return receipt;
    }
    void apply() {
        command(text("data.update"), QJsonObject{{text("draft"), draft}});
        window->statusBar()->showMessage(text("One Data update applied. No import, solver or AI was run."));
    }
    void attachProject() {
        connectedProject = window->project();
        auto* owner = connectedProject.data();
        QObject::connect(owner, &Project::requestSaveState, this, [this, owner](QXmlStreamWriter* writer) {
            if (!serializing || owner != connectedProject || owner != window->project()) return;
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
    void restoreBinding(const QString& path) {
        const auto binding = fileBinding(path);
        if (binding.isEmpty()) return;
        const auto acknowledgement = binding.value(text("document")).toObject();
        const auto oldService = service, oldIdentifier = identifier;
        if (service.isEmpty()) service = binding.value(text("service_url")).toString();
        identifier = acknowledgement.value(text("id")).toString();
        try {
            const auto current = request(documentPath());
            if (current.value(text("input_revision")) != acknowledgement.value(text("input_revision")) || current.value(text("draft")) != acknowledgement.value(text("draft")))
                throw std::runtime_error("The saved native view refers to an older Core input. Its file is preserved; reopen the matching Core revision explicitly.");
            baseline = current; draft = current.value(text("draft")).toObject(); savedAck = acknowledgement;
            importedReference = binding.value(text("result_reference")).toObject();
            channel = binding.value(text("response")).toString(); rows = binding.value(text("source_rows")).toArray();
            ++loadEpoch; attachProject();
            for (auto* part : connectedProject->children<Spreadsheet>()) if (part->name() == text("Core source")) sheet = part;
            for (auto* part : connectedProject->children<Worksheet>()) if (part->name() == text("Core curve")) sourceWorksheet = part;
            if (!sheet) throw std::runtime_error("The saved native source table is missing.");
            window->statusBar()->showMessage(text("Saved Core input and native view reopened. No calculation was submitted."));
        } catch (...) { connectedProject.clear(); service = oldService; identifier = oldIdentifier; throw; }
    }
    QString recoveryPath() const {
        const auto folder = QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + text("/caelab-data-recovery");
        QDir().mkpath(folder); return folder + text("/") + identifier + text(".json");
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
        if (window->project()) window->project()->setChanged(false);
        if (!window->openProject(temporary)) throw std::runtime_error("The native recovery view could not be reopened.");
        restoreBinding(temporary);
        pendingBinding = journal.value(text("binding")).toObject(); pendingPath = journal.value(text("path")).toString(); pendingXml = xml;
        connectedProject->setChanged(true); syncLocks();
        window->statusBar()->showMessage(text("Exact failed-save snapshot recovered. Retry replaces the view without another Core save."));
    }
    void importData() {
        if (pendingView()) throw std::runtime_error("Complete the pending exact view save first.");
        if (draft != baseline.value(text("draft")).toObject()) throw std::runtime_error("Apply local settings before explicitly preparing data.");
        const auto receipt = command(text("data.import"));
        const auto jobId = receipt.value(text("job")).toObject().value(text("id")).toString();
        if (jobId.isEmpty()) throw std::runtime_error("Import did not return a job identity.");
        QElapsedTimer deadline; deadline.start(); QJsonObject job;
        do {
            job = request(text("/api/workbench/jobs/") + jobId);
            const auto state = job.value(text("state")).toString();
            if (state == text("SUCCEEDED")) break;
            if (state == text("FAILED") || state == text("REJECTED") || deadline.elapsed() > 60000) throw std::runtime_error("The explicit data import did not succeed. Its job and original source remain retained.");
            QEventLoop delay; QTimer::singleShot(40, &delay, &QEventLoop::quit); delay.exec(QEventLoop::ExcludeUserInputEvents);
        } while (true);
        baseline = request(documentPath());
        importedReference = QJsonObject{{text("document_id"), identifier}, {text("job_id"), jobId}};
        connectedProject->setChanged(true);
        window->statusBar()->showMessage(text("Data explicitly prepared. Save to retain this exact result before Material transfer."));
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
    qint64 launchMaterial(const QString& materialId = {}) {
        const auto source = retainedSource();
        const auto context = request(text("/api/workbench/desktop"));
        auto environment = QProcessEnvironment::systemEnvironment();
        for (const auto* key : {"QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "CAELAB_DATA_TRIAL_REPORT", "CAELAB_DATA_CAPTURE_ONLY"}) environment.remove(text(key));
        const auto sdk = QString::fromUtf8(qgetenv("CAELAB_DONOR_SDK")); QStringList paths;
        for (const auto& path : environment.value(text("PATH")).split(QDir::listSeparator()))
            if (!path.startsWith(sdk.isEmpty() ? QLibraryInfo::path(QLibraryInfo::PrefixPath) : sdk, Qt::CaseInsensitive)) paths.append(path);
        environment.insert(text("PATH"), paths.join(QDir::listSeparator()));
        QProcess process; process.setProcessEnvironment(environment); process.setWorkingDirectory(context.value(text("repo_root")).toString());
        process.setProgram(context.value(text("python")).toString());
        QStringList arguments{text("-m"), text("apps.research.desktop"), text("--service"), service, text("material"), text("--observation"), QString::fromUtf8(QJsonDocument(source).toJson(QJsonDocument::Compact))};
        if (!materialId.isEmpty()) arguments << text("--document-id") << materialId;
        process.setArguments(arguments); qint64 pid = 0;
        if (!process.startDetached(&pid)) throw std::runtime_error("The Material process could not be requested. The saved source is preserved.");
        window->statusBar()->showMessage(text("Material window requested. Select a plan and review its test conditions; no fit or adoption has run."));
        return pid;
    }
    void workflow(const QString& reportPath, const QString& phase) {
        QJsonObject report;
        try {
            const auto target = QString::fromUtf8(qgetenv("CAELAB_DATA_VIEW_PATH"));
            if (phase == text("partial")) {
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
                    for (int col = 0; col < sheet->columnCount(); ++col) data.append(sheet->column(col)->valueAt(row)); values.append(data);
                }
                report = QJsonObject{{text("status"), text("PASS")}, {text("scope"), text("saved native Project cold reopen and exact Material receiver; no Data commands")},
                    {text("source"), source}, {text("material_pid"), pid}, {text("document"), before}, {text("native_values"), values}, {text("data_updates"), 0}};
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
            load();
            const auto original = draft;
            const auto generation = baseline.value(text("generation")).toInt();
            auto* view = dynamic_cast<SpreadsheetView*>(sheet->view());
            if (!view || rows.size() < 2) throw std::runtime_error("Trial requires at least two original rows.");
            view->setCellsSelected(1, 0, 1, sheet->columnCount() - 1);
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
                for (int column = 0; column < sheet->columnCount(); ++column) values.append(sheet->column(column)->valueAt(row));
                nativeValues.append(values);
            }
            report = QJsonObject{{text("status"), text("PASS")},
                {text("scope"), captureOnly ? text("read-only native table and curve capture of an externally saved Core document") : text("native source table, row selection, local Undo/Redo, one Core update")},
                {text("data_updates"), captureOnly ? 0 : 1},
                {text("source_rows"), rows}, {text("native_values"), nativeValues}, {text("curve_has_data"), curveHasData}, {text("document"), baseline}};
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
    static CaelabDataBridge* from(MainWin* host) {
        for (auto* child : host->children()) if (auto* bridge = dynamic_cast<CaelabDataBridge*>(child)) return bridge;
        return nullptr;
    }
    bool connected() const { return connectedProject && connectedProject == window->project(); }
    bool mayOpen(const QString& path) {
        if (!pendingApply.isEmpty() || pendingView()) {
            window->statusBar()->showMessage(text("Finish the pending exact save or command before switching documents.")); return false;
        }
        return true;
    }
    void opened(const QString& path) {
        guarded([this, path] { restoreBinding(path); });
        if (QString::fromUtf8(qgetenv("CAELAB_DATA_WORKFLOW_PHASE")) == text("reopen") && !workflowStarted) {
            workflowStarted = true;
            const auto report = QString::fromUtf8(qgetenv("CAELAB_DATA_TRIAL_REPORT"));
            QTimer::singleShot(0, this, [this, report] { workflow(report, text("reopen")); });
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
        menu = window->menuBar()->addMenu(text("Core Data trial"));
        readAction = menu->addAction(text("Read Core source"));
        excludeAction = menu->addAction(text("Exclude selected rows locally"));
        auto* applied = menu->addAction(text("Apply one Data update"));
        auto* saved = menu->addAction(text("Save Core and native view..."));
        auto* retry = menu->addAction(text("Retry pending command or exact view save"));
        auto* recovery = menu->addAction(text("Recover interrupted view save..."));
        auto* prepared = menu->addAction(text("Prepare data explicitly"));
        auto* material = menu->addAction(text("Use saved observation in Material..."));
        QObject::connect(readAction, &QAction::triggered, this, [this] { guarded([this] { load(); }); });
        QObject::connect(excludeAction, &QAction::triggered, this, [this] { guarded([this] { exclude(); }); });
        QObject::connect(applied, &QAction::triggered, this, [this] { guarded([this] { apply(); }); });
        QObject::connect(saved, &QAction::triggered, this, [this] {
            const auto path = QFileDialog::getSaveFileName(window, text("Save Core and native view"), connected() ? connectedProject->fileName() : QString(), text("LabPlot project (*.lml)"));
            if (!path.isEmpty()) guarded([this, path] { beginSave(path); commitView(); });
        });
        QObject::connect(retry, &QAction::triggered, this, [this] { guarded([this] {
            const auto operation = pendingApply.value(text("operation")).toString();
            if (operation == text("data.update")) apply();
            else if (operation == text("data.import")) importData();
            else { if (pendingXml.isEmpty()) beginSave(pendingPath); commitView(); }
        }); });
        QObject::connect(recovery, &QAction::triggered, this, [this] {
            const auto path = QFileDialog::getOpenFileName(window, text("Recover interrupted view save"), QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + text("/caelab-data-recovery"), text("Recovery snapshot (*.json)"));
            if (!path.isEmpty()) guarded([this, path] { recoverSave(path); });
        });
        QObject::connect(prepared, &QAction::triggered, this, [this] { guarded([this] { importData(); }); });
        QObject::connect(material, &QAction::triggered, this, [this] { guarded([this] {
            if (!pendingXml.isEmpty() || !pendingApply.isEmpty()) throw std::runtime_error("Finish the pending save or command first.");
            if (!connected() || connectedProject->fileName().isEmpty()) throw std::runtime_error("Save the connected native view before transfer.");
            beginSave(connectedProject->fileName()); commitView();
            const auto documents = request(text("/api/workbench/documents")).value(text("documents")).toArray();
            QStringList labels{text("New Material...")}, identifiers{QString()};
            for (const auto item : documents) { const auto doc = item.toObject();
                if (doc.value(text("kind")) == text("material") && doc.value(text("draft")).toObject().value(text("backend")) == text("material.felupe")) {
                    labels.append(doc.value(text("title")).toString()); identifiers.append(doc.value(text("id")).toString());
                }
            }
            bool accepted = false; const auto choice = QInputDialog::getItem(window, text("Use in Material"), text("Review observation in"), labels, 0, false, &accepted);
            if (accepted) launchMaterial(identifiers.value(labels.indexOf(choice)));
        }); });
        window->installEventFilter(this);
        if (window->project() && !window->project()->fileName().isEmpty()) guarded([this] { restoreBinding(window->project()->fileName()); });
        const auto report = QString::fromUtf8(qgetenv("CAELAB_DATA_TRIAL_REPORT"));
        const auto phase = QString::fromUtf8(qgetenv("CAELAB_DATA_WORKFLOW_PHASE"));
        if (!report.isEmpty() && phase != text("reopen")) QTimer::singleShot(300, this, [this, report, phase] { if (phase.isEmpty()) trial(report); else workflow(report, phase); });
        if (!report.isEmpty() && phase == text("reopen")) QTimer::singleShot(15000, this, [this, report] { if (!workflowStarted) { workflowStarted = true; workflow(report, text("reopen")); } });
    }
};
