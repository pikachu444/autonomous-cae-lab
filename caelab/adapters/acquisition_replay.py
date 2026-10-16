"""Bounded binary-line CSV replay; no equipment protocol is implied.

Supported records are UTF-8 CSV with one physical line per sample and explicit
sequence,timestamp columns. Multiline/quoted records are rejected and retained.
"""
import csv
import math
from pathlib import Path

from ..acquisition_session import MAX_PACKET_BYTES, MAX_BATCH, MODE
from ..evaluation import file_hash


class RecordedReplay:
    mode = MODE

    def __init__(self, path, channels, *, expected_sha256=None, cursor=None):
        self.path = Path(path)
        self.stream = None
        try:
            self.sha256 = file_hash(self.path)
            if expected_sha256 is not None and self.sha256 != expected_sha256:
                raise ValueError('기록 원파일이 변경되었습니다. 기존 취득을 보존하고 새 취득으로 여세요.')
            self.stream = self.path.open('rb')
            header = self.stream.readline(MAX_PACKET_BYTES + 1)
            if len(header) > MAX_PACKET_BYTES or b'"' in header:
                raise ValueError('기록 파일 header는 64 KiB 이하의 단일 UTF-8 CSV 행이어야 합니다.')
            self.header = next(csv.reader([header.decode('utf-8-sig').rstrip('\r\n')], strict=True))
            self.channels = list(channels)
            if len(set(self.header)) != len(self.header) or not {'sequence', 'timestamp', *channels} <= set(self.header):
                raise ValueError('CSV에 서로 다른 sequence, timestamp와 계획 채널 열이 필요합니다.')
            self.start_cursor = self.stream.tell()
            if cursor is not None:
                if type(cursor) is not int or not self.start_cursor <= cursor <= self.path.stat().st_size:
                    raise ValueError('저장된 재생 위치가 원파일 범위를 벗어납니다.')
                self.stream.seek(cursor)
            self.row = 0
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def batch(self, count=MAX_BATCH):
        if type(count) is not int or not 1 <= count <= MAX_BATCH:
            raise ValueError('batch는 1–64개 표본입니다.')
        result = []
        for _ in range(count):
            offset = self.stream.tell()
            raw = self.stream.readline(MAX_PACKET_BYTES + 1)
            if not raw:
                break
            if len(raw) > MAX_PACKET_BYTES:
                # Do not acknowledge a truncated record or advance its prefix.
                self.stream.seek(offset)
                raise ValueError('표본 한 행이 64 KiB를 넘습니다. 원파일은 보존되며 이 위치에서 중단합니다.')
            self.row += 1
            packet = {'raw': raw, 'cursor': self.stream.tell(), 'source_row': offset}
            try:
                if b'"' in raw:
                    raise ValueError('여러 행/따옴표 CSV는 지원하지 않습니다.')
                row = next(csv.reader([raw.decode('utf-8').rstrip('\r\n')], strict=True))
                if len(row) != len(self.header):
                    raise ValueError('header와 표본의 열 수가 다릅니다.')
                values = dict(zip(self.header, row))
                seq = int(values['sequence'])
                if not values['sequence'].isdigit() or not 0 <= seq <= 9223372036854775807:
                    raise ValueError('sequence는 음이 아닌 64-bit 정수여야 합니다.')
                timestamp = float(values['timestamp'])
                if not math.isfinite(timestamp):
                    raise ValueError('timestamp는 유한 초 값이어야 합니다.')
                quality = []
                for channel in self.channels:
                    try:
                        if not math.isfinite(float(values[channel])):
                            quality.append(channel + ':NONFINITE')
                    except ValueError:
                        quality.append(channel + ':NONNUMERIC')
                packet.update(sequence=seq, timestamp=timestamp,
                    values={c: values[c] for c in self.channels}, quality=quality)
            except (ValueError, UnicodeError, csv.Error) as error:
                packet['error'] = str(error)
            result.append(packet)
        return result
