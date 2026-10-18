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
#include <stdexcept>
#include <limits>
#include <functional>

class CaelabDataBridge : public QObject {
    static QString text(const char* value) { return QString::fromUtf8(value); }
    MainWin* window;
    QNetworkAccessManager network;
    QPointer<Spreadsheet> sheet;
    QPointer<Worksheet> sourceWorksheet;
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
        if (!pendingApply.isEmpty() && lockedActions.isEmpty()) {
            for (auto* action : window->findChildren<QAction*>()) {
                if (action->parent() == menu || action == menu->menuAction()) continue;
                lockedActions.append({action, action->isEnabled()}); action->setEnabled(false);
                QObject::connect(action, &QAction::changed, this, [this, action] {
                    if (!pendingApply.isEmpty() && action->isEnabled()) action->setEnabled(false);
                });
            }
        } else if (pendingApply.isEmpty() && !lockedActions.isEmpty()) {
            const auto restore = lockedActions; lockedActions.clear();
            for (const auto& entry : restore) if (entry.first) entry.first->setEnabled(entry.second);
        }
        readAction->setEnabled(pendingApply.isEmpty()); excludeAction->setEnabled(pendingApply.isEmpty());
    }
    bool eventFilter(QObject* watched, QEvent* event) override {
        if (watched == window && event->type() == QEvent::Close && !pendingApply.isEmpty()) {
            static_cast<QCloseEvent*>(event)->ignore();
            window->statusBar()->showMessage(text("Confirm the pending Core Apply before closing this temporary view."));
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
        void undo() override { if (bridge && bridge->loadEpoch == epoch && bridge->pendingApply.isEmpty()) bridge->draft = before; }
        void redo() override { if (bridge && bridge->loadEpoch == epoch && bridge->pendingApply.isEmpty()) bridge->draft = after; }
    };
    void load() {
        if (!pendingApply.isEmpty()) throw std::runtime_error("Confirm pending Apply before reading another Core input.");
        if (service.isEmpty() || identifier.isEmpty())
            throw std::runtime_error("Set CAELAB_SERVICE_URL and CAELAB_DATA_DOCUMENT_ID for the bounded donor trial.");
        baseline = request(documentPath()); draft = baseline.value(text("draft")).toObject(); ++loadEpoch;
        auto mapping = draft.value(text("mapping")).toObject();
        const auto channels = mapping.value(text("columns")).toObject();
        channel = channels.keys().value(0);
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
        if (!pendingApply.isEmpty()) throw std::runtime_error("Confirm the pending Apply before editing again.");
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
    void apply() {
        if (pendingApply.isEmpty()) {
            const auto current = request(documentPath());
            if (current.value(text("session_id")) != baseline.value(text("session_id")) || current.value(text("generation")) != baseline.value(text("generation")))
                throw std::runtime_error("Core input changed. The local buffer has been preserved; reopen or recover it.");
            pendingApply = QJsonObject{{text("operation"), text("data.update")}, {text("arguments"), QJsonObject{{text("draft"), draft}}},
                {text("session_id"), baseline.value(text("session_id"))}, {text("expected_generation"), baseline.value(text("generation"))},
                {text("command_id"), QString(text("C") + QUuid::createUuid().toString(QUuid::Id128))}};
        }
        const auto receipt = request(documentPath() + text("/commands"), &pendingApply);
        const auto acknowledged = receipt.value(text("document")).toObject();
        const auto current = request(documentPath());
        for (const auto* key : {"session_id", "generation", "input_revision", "draft"})
            if (current.value(text(key)) != acknowledged.value(text(key)))
                throw std::runtime_error("Apply is acknowledged but Core has since changed. Keep the local buffer and recover explicitly.");
        baseline = current; pendingApply = {};
        syncLocks();
        window->statusBar()->showMessage(text("One Data update applied. No import, solver or AI was run."));
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
    explicit CaelabDataBridge(MainWin* host) : QObject(host), window(host), network(this),
        service(QString::fromUtf8(qgetenv("CAELAB_SERVICE_URL"))), identifier(QString::fromUtf8(qgetenv("CAELAB_DATA_DOCUMENT_ID"))) {
        menu = window->menuBar()->addMenu(text("Core Data trial"));
        readAction = menu->addAction(text("Read Core source"));
        excludeAction = menu->addAction(text("Exclude selected rows locally"));
        auto* applied = menu->addAction(text("Apply one Data update"));
        QObject::connect(readAction, &QAction::triggered, this, [this] { guarded([this] { load(); }); });
        QObject::connect(excludeAction, &QAction::triggered, this, [this] { guarded([this] { exclude(); }); });
        QObject::connect(applied, &QAction::triggered, this, [this] { guarded([this] { apply(); }); });
        window->installEventFilter(this);
        const auto report = QString::fromUtf8(qgetenv("CAELAB_DATA_TRIAL_REPORT"));
        if (!report.isEmpty()) QTimer::singleShot(300, this, [this, report] { trial(report); });
    }
};
