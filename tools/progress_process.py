"""Drain FFmpeg pipes safely while publishing its actual encoded presentation time."""
import subprocess
import threading
import time


def measured_process(command, timeout, cwd, duration):
    from progress_records import advance, child_environment, context
    if not context():
        # Standalone rendering still works without an observational record.
        result = subprocess.run(command, cwd=cwd, timeout=timeout, capture_output=True, text=True,
                                encoding='utf-8', errors='replace')
    else:
        actual = [command[0], '-progress', 'pipe:2', '-nostats', *command[1:]]
        child = subprocess.Popen(actual, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding='utf-8', errors='replace', env=child_environment())
        output, errors, fields = [], [], {}
        current = context()
        def drain(stream, target, measured=False):
            from progress_records import ACTIVE
            token = ACTIVE.set(current)
            last = 0
            try:
                for line in stream:
                    target.append(line)
                    if not measured or '=' not in line:
                        continue
                    key, value = line.strip().split('=', 1)
                    if key in ('out_time_us', 'frame', 'fps', 'speed'):
                        fields[key] = value
                    if key == 'progress' and (value == 'end' or time.monotonic() - last >= 1):
                        try:
                            seconds = max(0, int(fields.get('out_time_us', 0)) / 1000000)
                            advance(seconds, duration, 'seconds', 'Encoding video',
                                    frame=int(fields.get('frame', 0)), speed=fields.get('speed'), fps=fields.get('fps'))
                            last = time.monotonic()
                        except (ValueError, TypeError):
                            pass
            finally:
                ACTIVE.reset(token)
                stream.close()
        readers = [threading.Thread(target=drain, args=(child.stdout, output), daemon=True),
                   threading.Thread(target=drain, args=(child.stderr, errors, True), daemon=True)]
        for reader in readers:
            reader.start()
        try:
            child.wait(timeout=timeout)
        except BaseException:
            child.kill()
            child.wait()
            raise
        finally:
            for reader in readers:
                reader.join(timeout=5)
        result = subprocess.CompletedProcess(command, child.returncode, ''.join(output), ''.join(errors))
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {command[0]}\n{result.stderr[-6000:]}')
    return result
