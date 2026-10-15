"""Image blocks in the existing Report preview/PDF/Markdown pipeline."""
import base64
from html import escape

from caelab.report_image import caption, image_options, validate_content


def image_markdown(content, section):
    data = validate_content(content)
    if not image_options(section)['show']:
        return ''
    width = image_options(section)['width_percent']
    # Self-contained output: no new asset folder or mutable Post pathname.
    return ('<img alt="' + escape(caption(content['snapshot']), quote=True) +
            '" style="width:' + str(width) + '%;height:auto" src="data:image/png;base64,' +
            base64.b64encode(data).decode('ascii') + '" />')


def availability_message(asset):
    if asset.get('retained_preview_only'):
        return '보존 자산 검증 실패 — 마지막으로 검증한 화면 사본입니다. 복구 전 초안이며 새 캡처가 아닙니다.'
    if asset.get('source_status') == 'SNAPSHOT_UNAVAILABLE':
        return '보존 자산을 읽거나 검증하지 못했습니다. 기존 섹션의 본문과 판단은 유지됩니다.'
    if asset.get('source_status') != 'AVAILABLE':
        noun = '이미지와 조건' if asset.get('content', {}).get('kind') == 'post_image' else '내용과 조건'
        return '원자료 확인 불가 — 보고서에 고정한 ' + noun + '입니다. 출처를 명시적으로 복구하세요.'
    return ''


def insert_image(document, cursor, content, section, key):
    from PySide6.QtCore import QByteArray, QUrl
    from PySide6.QtGui import QImage, QTextDocument, QTextImageFormat
    data = validate_content(content)
    options = image_options(section)
    if not options['show']:
        return
    image = QImage.fromData(QByteArray(data), 'PNG')
    if image.isNull():
        raise ValueError('보존 PNG를 실제 이미지로 읽지 못했습니다. 기존 출력은 유지됩니다.')
    width, height = content['snapshot']['pixel_size']
    factor = min(515 * options['width_percent'] / 100 / width, 650 / height)
    url = QUrl(key)
    document.addResource(QTextDocument.ResourceType.ImageResource, url, image)
    fmt = QTextImageFormat(); fmt.setName(url.toString())
    fmt.setWidth(width * factor); fmt.setHeight(height * factor)
    cursor.insertImage(fmt); cursor.insertBlock()
