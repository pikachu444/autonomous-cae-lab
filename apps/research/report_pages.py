"""One native page composition for preview and PDF; no WebEngine."""
from io import BytesIO
from pathlib import Path
import base64
import math
import os
import tempfile

from PySide6.QtCore import QByteArray, QUrl, QSizeF
from PySide6.QtGui import QFont, QImage, QTextCharFormat, QTextCursor, QTextDocument, QTextImageFormat, QTextTableFormat, QPageSize
from PySide6.QtPrintSupport import QPrinter
from .experiment_labels import sample_reason, REDUCTIONS


def value_text(value):
    if value is None:
        return '미확인'
    if type(value) is float:
        return format(value, '.9g') if math.isfinite(value) else str(value)
    if isinstance(value, list):
        return ', '.join(value_text(v) for v in value)
    return str(value)


def physical_text(key, value):
    """Display known physical terms; retain user-defined names and source values."""
    meanings = {
        'measure': {'force':'힘', 'torque':'토크', 'displacement':'변위', 'stress':'응력',
                    'infinitesimal_Cauchy':'미소변형 Cauchy 응력'},
        'component': {'x':'X 방향', 'y':'Y 방향', 'z':'Z 방향',
                      **{v:v.upper() for v in ('xx','yy','zz','xy','yx','xz','zx','yz','zy')}},
        'frame': {'lab':'실험실 좌표', 'laboratory':'실험실 좌표',
                  'material_cartesian':'재료 직교좌표', 'global':'전체 좌표', 'local':'국부 좌표'},
        'location': {'material_point':'재료점'},
        'axis': {'time':'시간', 'frequency':'주파수'},
    }
    if isinstance(value, dict) and isinstance(value.get('label'), str):
        return value['label']
    return meanings.get(key, {}).get(value, value_text(value)) if isinstance(value, str) else value_text(value)


def verdict_text(value):
    return {'UNKNOWN':'미확인', 'PASS':'통과', 'FAIL':'실패', 'PASSED':'통과',
            'FAILED':'실패', 'NOT_EVALUATED':'미평가', 'ACCEPTABLE':'적합',
            'UNACCEPTABLE':'부적합', 'VALIDATED':'검증됨'}.get(value, value_text(value))


def blocks(content):
    """Semantic blocks use only the frozen selected payload."""
    kind = content.get('kind')
    if kind == 'numerical_candidate_evidence':
        from .numerical_candidate_evidence_report import candidate_evidence_blocks
        yield from candidate_evidence_blocks(content)
        return
    if content.get('report_intent') == 'METADATA_ONLY_NOT_A_SUCCESS_JUDGMENT':
        yield ('paragraph', '후보 요약입니다. 원행별 상세 결과와 계수 채택은 이 요약으로 확인하지 않았습니다.')
    if kind == 'post_image':
        from caelab.report_image import caption, validate_content
        validate_content(content)
        yield ('paragraph', caption(content['snapshot']))
        yield ('image', content)
        return
    if kind == 'comparison':
        comparison=content['comparison']['comparison']
        observation=comparison['observation']; axes=observation.get('axes',[])
        x=axes[0]['values'] if len(axes)==1 else list(range(len(observation['value'])))
        xlabel=physical_text('axis',axes[0]['name'])+' ['+axes[0]['unit']+']' if len(axes)==1 else '표본'
        rows=observation.get('source_rows',list(range(len(x))))
        observed=observation['value']; predicted=comparison['prediction']; mask=comparison['mask']
        physical=[p-o if ok and p is not None and o is not None else None for p,o,ok in zip(predicted,observed,mask)]
        yield ('paragraph','관측과 계산 비교 / 전체 비교 RMSE '+value_text(comparison.get('rmse'))+' ['+
            comparison['unit']+'] / 정렬: '+str(comparison.get('alignment_policy',comparison.get('method'))))
        for label,values in [('관측',observed),('계산',predicted),('계산 − 관측',physical)]:
            yield ('curve',{'x':x,'y':values,'source_rows':rows,'mask':mask,
                'segments':comparison.get('observation_segments'),'x_label':xlabel,'y_label':label+' ['+comparison['unit']+']'})
        yield ('table',(['원행',xlabel,'관측 ['+comparison['unit']+']','계산 ['+comparison['unit']+']','차이 ['+comparison['unit']+']'],
            [[row,t,o,p,d] for row,t,o,p,d in zip(rows,x,observed,predicted,physical)]))
        return
    if kind == 'knowledge':
        source = content['source']
        yield ('paragraph', source.get('title', '문헌'))
        for segment in source.get('segments', []):
            yield ('paragraph', segment.get('text', ''))
        for issue in source.get('failed_segments', []):
            yield ('paragraph', '읽지 못한 원문: ' + str(issue.get('reason', '미확인')))
        return
    if kind == 'expert_turn':
        from .discussion_view import turn_text, author_label
        turn = content['turn']
        yield ('paragraph', author_label(turn))
        yield ('paragraph', turn_text(turn))
        return
    if kind == 'document':
        document = content['document']
        draft = document['draft']
        if document['kind'] == 'study':
            yield ('paragraph', draft.get('question', ''))
            for group in ('hypotheses', 'decisions', 'next_observations'):
                for row in draft.get(group, []):
                    yield ('paragraph', '\n'.join(str(row.get(key, '')) for key in
                        ('title', 'question', 'statement', 'note', 'status') if row.get(key)))
        else:
            yield ('paragraph', document['title'] + '\n저장된 원 문서는 원자료 열기로 확인하세요.')
        return
    result = content.get('result', {})
    execution = {'SUCCEEDED':'계산 완료', 'FAILED':'계산 실패', 'PARTIAL_FAILURE':'일부 계산 실패',
                 'CANCELLED':'계산 취소', 'INTERRUPTED':'계산 중단', 'REJECTED':'계산 불가',
                 'RUNNING':'계산 중', 'PENDING':'계산 대기', 'PREDICTED':'대리모델 예측',
                 'UNKNOWN':'계산 상태 미확인'}.get(result.get('execution_status','UNKNOWN'), '계산 상태 미확인')
    yield ('paragraph', execution+'. 물리 판정 '+verdict_text(result.get('qualification','UNKNOWN'))+
           '. 공학적 승인 없음.')
    if result.get('failure_reason'):
        yield ('paragraph', str(result['failure_reason']))
    checks=result.get('checks', [])
    if isinstance(checks, dict):
        checks=[dict(value, name=key) if isinstance(value, dict) else {'name':key,'status':value}
                for key,value in checks.items()]
    if 'converged' in result:
        yield ('paragraph','수렴: '+('수렴' if result['converged'] is True else
              '미수렴' if result['converged'] is False else '미확인'))
    if result.get('termination_reason'):
        yield ('paragraph','종료 이유: '+str(result['termination_reason']))
    if checks:
        yield ('table', (['확인 항목','판정','값','단위','기준','근거'],
            [[c.get('name',c.get('id','확인')),
              verdict_text(c.get('status', '통과' if c.get('passed') is True else '실패' if c.get('passed') is False else '미확인')),
              c.get('value'),c.get('unit',''),
              ' / '.join(label+' '+value_text(c[key]) for key,label in
                  (('operator','비교'),('limit','한계'),('tolerance','허용차'),('minimum','하한'),
                   ('maximum','상한'),('expected','기준값')) if key in c),
              c.get('reason',c.get('message',''))] for c in checks if isinstance(c,dict)]))
    for key in ('candidates','predictions'):
        for index,row in enumerate(result.get(key,[])):
            predicted=key=='predictions' or row.get('prediction_status')=='PREDICTED' or row.get('execution_status')=='PREDICTED'
            yield ('paragraph', ('대리모델 예측 — 실제 계산 아님' if predicted else '선택한 실제 후보')+' '+str(index+1))
            yield ('table', (['입력','값'], [[k,v] for k,v in row.get('values',{}).items()]))
            yield from blocks({'kind':'result','result':row})
    if 'objective' in result:
        yield ('table', (['저장된 목적값','제약 만족'],[[result['objective'],
            '예' if result.get('feasible') is True else '아니오' if result.get('feasible') is False else '미확인']]))
    if result.get('constraint_residuals'):
        yield ('table', (['제약 순서','정규화 잔차'],[[i+1,v] for i,v in enumerate(result['constraint_residuals'])]))
    if result.get('response_reductions'):
        yield ('paragraph','저장된 축약값 — 원 곡선을 대신하지 않습니다.')
        yield ('table', (['응답','축약','값','단위','성분','위치','정의','좌표계'],
            [[r['response'],REDUCTIONS.get(r.get('reduction'),str(r.get('reduction'))),r.get('value'),
              r.get('unit'),physical_text('component',r.get('component')),physical_text('location',r.get('location')),
              physical_text('measure',r.get('measure')),physical_text('frame',r.get('frame'))]
             for r in result['response_reductions']]))
    for name, response in result.get('responses', {}).items():
        yield ('paragraph', name + ' [' + str(response.get('unit', '미확인')) + ']\n' +
               ', '.join(label+': '+physical_text(key,response[key]) for key,label in
                   (('measure','물리량'),('component','성분'),('location','측정 위치'),('frame','좌표계')) if response.get(key)))
        values, axes = response.get('value'), response.get('axes', [])
        if isinstance(values, list):
            coordinates = axes[0].get('values', []) if len(axes) == 1 else []
            rows = response.get('source_rows', list(range(len(values))))
            supplied_mask=response.get('mask')
            mask=[False if response.get('valid') is False else
                  (supplied_mask[i] if isinstance(supplied_mask,list) and i<len(supplied_mask) else None)
                  for i in range(len(values))]
            if response.get('valid') is False or response.get('reason'):
                yield ('paragraph', '응답 판정: '+('무효' if response.get('valid') is False else '미확인')+
                       ' / '+str(response.get('reason',response.get('invalid_reason','원자료 확인 필요'))))
            if len(coordinates) == len(values) and not response.get('calibration'):
                yield ('curve', {'x': coordinates, 'y': values, 'source_rows': rows,
                    'mask': mask, 'segments': response.get('segments'),
                    'x_label': physical_text('axis',axes[0].get('name', '')) + ' [' + axes[0].get('unit', '') + ']',
                    'y_label': name + ' [' + response.get('unit', '') + ']'})
            headers = ['원행', physical_text('axis',axes[0].get('name', '축')) + ' [' + axes[0].get('unit', '') + ']' if axes else '위치',
                       name + ' [' + response.get('unit', '') + ']', '유효']
            yield ('table', (headers, [[rows[i] if i < len(rows) else i,
                coordinates[i] if i < len(coordinates) else '', y,
                '유효' if mask[i] is True else ('무효/제외' if mask[i] is False else '행 판정 없음')] for i, y in enumerate(values)]))
            raw = response.get('raw_samples')
            if isinstance(raw, dict):
                calibration = response.get('calibration') or {}
                if calibration:
                    raw_x = raw.get('transformed_axis') or raw['source_rows']
                    x_label = (physical_text('axis',axes[0].get('name',''))+' ['+axes[0].get('unit','')+']') if axes else '원행'
                    yield ('curve', {'x':raw_x, 'y':raw['value'], 'source_rows':raw['source_rows'],
                        'x_label':x_label, 'y_label':'원값 ['+calibration['input_unit']+']'})
                    yield ('curve', {'x':raw_x, 'y':raw['transformed_value'], 'source_rows':raw['source_rows'],
                        'mask':raw['calibration_valid'], 'out_of_range':raw['calibration_out_of_range'],
                        'saturated':raw['sensor_saturated'], 'x_label':x_label,
                        'y_label':'교정값 ['+calibration['output_unit']+']'})
                    u = calibration.get('uncertainty')
                    yield ('paragraph', '교정: y = '+value_text(calibration['a'])+' ['+calibration['output_unit']+'/'+
                        calibration['coefficient_input_unit']+'] × (x − '+value_text(calibration['x0'])+' ['+
                        calibration['x0_unit']+']) + '+value_text(calibration['b'])+' ['+calibration['output_unit']+']')
                    yield ('paragraph', ('제공 불확실성: '+value_text(u['value'])+' ['+u['unit']+'] / '+
                        {'standard':'표준','expanded':'확장'}.get(u['kind'],'종류 미확인')+' / k='+value_text(u['k'])+' / '+
                        {'UNKNOWN':'상관 미확인','independent_declared':'독립이라고 제공됨','correlated_declared':'상관이 있다고 제공됨'}[u['correlation']])
                        if u else '측정 불확실성: 미제공')
                def sample(key, i, default=None):
                    values=raw.get(key)
                    return values[i] if isinstance(values,list) and i<len(values) else default
                def state(value):
                    return '예' if value is True else ('아니오' if value is False else '미확인')
                yield ('table', (['원행', '원값 ['+str(calibration.get('input_unit','미확인'))+']',
                    '교정값 ['+response.get('unit','')+']', '품질 유효', '계산 사용', '표시', '사유'],
                    [[row, sample('value',i), sample('transformed_value',i),
                      state(sample('quality_valid',i)),state(sample('calculation_valid',i)),
                      state(sample('display_visible',i)),
                      ' / '.join(sample_reason(sample(key,i)) for key in ('quality_reasons','exclusion_reasons')
                                 if sample(key,i))]
                     for i, row in enumerate(raw.get('source_rows', []))]))
        elif values is not None:
            yield ('table', (['응답', '값', '단위', '판정', '사유'], [[name, values, response.get('unit'),
                '유효' if response.get('valid') is True else ('무효' if response.get('valid') is False else '미확인'),
                response.get('reason',response.get('invalid_reason',''))]]))
    if result.get('kind') in {'experiment_uncertainty','experiment_identification'}:
        from caelab.experiment_analysis_reporting import blocks as experiment_blocks
        yield from experiment_blocks(result)
        return
    diagnosis = result.get('identification', {})
    if diagnosis:
        yield ('paragraph', '식별 진단: ' + str(diagnosis.get('status', 'UNKNOWN')) +
            '\n선택 피팅점의 국소 1차 응답 구분이며 전역 유일성·측정 불확실성은 미확인입니다.')
        yield ('table', (['계수', '값', '단위', '국소 구분'],
            [[p['id'], diagnosis.get('parameter_values', {}).get(p['id']), p.get('unit'), p.get('status')]
             for p in diagnosis.get('parameters', [])]))


def plot_bytes(curve):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(figsize=(7.1, 3.1), dpi=130)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    x, y = curve['x'], curve['y']
    mask = curve.get('mask')
    if mask is None: mask = [True]*len(y)
    yy = [v if i < len(mask) and mask[i] and type(v) in (int, float) and math.isfinite(v)
          else float('nan') for i, v in enumerate(y)]
    segments = curve.get('segments')
    if segments:
        positions = {row: i for i, row in enumerate(curve.get('source_rows', []))}
        for segment in segments:
            indices = [positions[row] for row in segment.get('source_rows', []) if row in positions]
            ax.plot([x[i] for i in indices], [yy[i] for i in indices], 'o-', markersize=2)
    else:
        ax.plot(x, yy, 'o-', markersize=2)
    unknown=[i for i,v in enumerate(y) if i<len(mask) and mask[i] is None
             and type(v) in (int,float) and math.isfinite(v)]
    if unknown:
        ax.scatter([x[i] for i in unknown],[y[i] for i in unknown],marker='x',color='gray',label='행 판정 없음')
    for flag, marker, label in [('out_of_range','o','범위 밖'),('saturated','x','포화')]:
        indices=[i for i,value in enumerate(curve.get(flag,[])) if value and type(y[i]) in (int,float) and math.isfinite(y[i])]
        if indices:
            style={'facecolors':'none','edgecolors':'red'} if marker=='o' else {'color':'red'}
            ax.scatter([x[i] for i in indices],[y[i] for i in indices],marker=marker,label=label,**style)
    if unknown or curve.get('out_of_range') or curve.get('saturated'): ax.legend()
    ax.set_xlabel(curve['x_label']); ax.set_ylabel(curve['y_label'])
    ax.grid(alpha=.2); fig.tight_layout()
    stream = BytesIO(); fig.savefig(stream, format='png')
    return stream.getvalue()


def compose(draft, assets, font):
    document = QTextDocument()
    document.setDefaultFont(font)
    document.setPageSize(QSizeF(595, 842)); document.setDocumentMargin(36)
    document.section_positions = {}
    cursor = QTextCursor(document)
    normal = QTextCharFormat(); normal.setFont(font)
    heading = QTextCharFormat(normal); heading.setFontPointSize(18); heading.setFontWeight(QFont.Weight.Bold)
    subheading = QTextCharFormat(normal); subheading.setFontPointSize(13); subheading.setFontWeight(QFont.Weight.Bold)
    table_heading = QTextCharFormat(normal); table_heading.setFontWeight(QFont.Weight.Bold)
    def paragraph(text, style=normal):
        cursor.insertText(str(text), style); cursor.insertBlock()
    paragraph(draft['title'], heading)
    images = 0
    for section in draft['sections']:
        if not section['include']:
            continue
        document.section_positions[section['id']] = cursor.position()
        paragraph(section['title'], subheading)
        paragraph(section['text'])
        asset = assets.get((section.get('asset') or {}).get('id'))
        if section.get('asset') and (not asset or 'content' not in asset):
            paragraph('보존 자료를 읽지 못했습니다. 이 섹션의 원자료를 확인하세요.')
            continue
        if not asset:
            continue
        if asset.get('source_status') != 'AVAILABLE':
            from .report_image_pages import availability_message
            paragraph(availability_message(asset))
        for kind, value in blocks(asset['content']):
            if kind == 'paragraph':
                paragraph(value)
            elif kind == 'image':
                from .report_image_pages import insert_image
                insert_image(document, cursor, value, section, 'report-image:' + str(images))
                images += 1
            elif kind == 'curve' and section['curve']:
                png = plot_bytes(value)
                image = QImage.fromData(QByteArray(png), 'PNG')
                key = QUrl('report-image:' + str(images)); images += 1
                document.addResource(QTextDocument.ResourceType.ImageResource, key, image)
                fmt = QTextImageFormat(); fmt.setName(key.toString()); fmt.setWidth(515); fmt.setHeight(225)
                cursor.insertImage(fmt); cursor.insertBlock()
            elif kind == 'table' and section['table']:
                headers, rows = value
                if not rows:
                    continue
                fmt = QTextTableFormat(); fmt.setHeaderRowCount(1); fmt.setCellPadding(5)
                fmt.setCellSpacing(2); fmt.setBorder(.4); fmt.setWidth(515)
                table = cursor.insertTable(len(rows)+1, len(headers), fmt)
                for i, row in enumerate([headers, *rows]):
                    for j, v in enumerate(row):
                        cell = table.cellAt(i, j).firstCursorPosition()
                        cell.insertText(value_text(v), table_heading if i == 0 else normal)
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertBlock()
        paragraph('표시는 유효숫자 9자리. 원값·단위·선택은 보고서 자료에 보존됩니다.')
    return document


def markdown(draft, assets):
    def escape(s):
        return str(s).replace('|', r'\|').replace('\n', '<br>')
    lines = ['# ' + draft['title'], '', '공학 승인: NOT_RELEASED', '']
    for section in draft['sections']:
        if not section['include']:
            continue
        lines += ['## ' + section['title'], '', section['text'], '']
        asset = assets.get((section.get('asset') or {}).get('id'))
        if not asset:
            if section.get('asset'):
                lines += ['보존 자료를 읽지 못했습니다.', '']
            continue
        if asset.get('source_status') != 'AVAILABLE':
            from .report_image_pages import availability_message
            lines += [availability_message(asset), '']
        for kind, value in blocks(asset.get('content', {})):
            if kind == 'paragraph':
                lines += [value, '']
            elif kind == 'image':
                from .report_image_pages import image_markdown
                lines += [image_markdown(value, section), '']
            elif kind == 'curve' and section['curve']:
                lines += ['![고정한 자료의 곡선](data:image/png;base64,' +
                          base64.b64encode(plot_bytes(value)).decode('ascii') + ')', '']
            elif kind == 'table' and section['table']:
                headers, rows = value
                lines += ['| ' + ' | '.join(map(escape, headers)) + ' |',
                          '| ' + ' | '.join(['---']*len(headers)) + ' |']
                lines += ['| ' + ' | '.join(escape(value_text(v)) for v in row) + ' |' for row in rows]
                lines.append('')
        lines += ['<details><summary>정확한 원자료 참조</summary>', '',
                  chr(96)*3 + 'json', __import__('json').dumps(asset.get('reference'), ensure_ascii=False, indent=2),
                  chr(96)*3, '</details>', '']
    return '\n'.join(lines)


def atomic_export(path, write):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.cae-report-', suffix=path.suffix, dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        write(temporary)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise OSError('출력 파일이 비어 있습니다.')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def pdf_document(document, path):
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4)); printer.setFullPage(True)
    printer.setOutputFileName(str(path))
    document.print_(printer)
