#!/usr/bin/env python3
"""AISA dual-key round-robin (slots A/B). Secrets stay in mode-0600 files; logs use slot ids only."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

BASE_DIR = Path(os.environ.get(
    'AISA_KEYRING_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '.aisa'),
))
KEYS_PATH = Path(os.environ.get('AISA_KEYS_PATH', str(BASE_DIR / 'keys.env')))
STATE_PATH = Path(os.environ.get('AISA_RR_STATE_PATH', str(BASE_DIR / 'rr_state.json')))
SLOTS = ('A', 'B')

_MEM_LOCK = threading.Lock()
_KEYS_CACHE = None  # type: ignore


class AisaKeyringError(RuntimeError):
    pass


def _read_keys_unlocked() -> dict:
    global _KEYS_CACHE
    if _KEYS_CACHE is not None:
        return _KEYS_CACHE
    keys = {}
    if KEYS_PATH.exists():
        for line in KEYS_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k, v = k.strip(), v.strip().strip('"\'')
            if k in ('AISA_KEY_A', 'AISA_KEY_B') and v:
                keys[k[-1]] = v  # 'A' / 'B'
    # Legacy single-key fallback from env / .env (slot A only) if keys file missing A
    if 'A' not in keys:
        k = os.environ.get('AISA_API_KEY')
        if not k:
            envf = Path(os.path.dirname(os.path.abspath(__file__))) / '.env'
            if envf.exists():
                for line in envf.read_text().splitlines():
                    if line.strip().startswith('AISA_API_KEY='):
                        k = line.split('=', 1)[1].strip().strip('"\'')
                        break
        if k:
            keys['A'] = k
    if not keys:
        raise AisaKeyringError('no AISA keys configured')
    _KEYS_CACHE = keys
    return keys


def clear_cache() -> None:
    global _KEYS_CACHE
    with _MEM_LOCK:
        _KEYS_CACHE = None


def _default_state() -> dict:
    return {
        'version': 1,
        'slots': list(SLOTS),
        'next_index': 0,
        'disabled': {},
        'updated_at': None,
    }


def _load_state(fh) -> dict:
    fh.seek(0)
    raw = fh.read()
    if not raw.strip():
        return _default_state()
    try:
        st = json.loads(raw)
    except json.JSONDecodeError:
        return _default_state()
    if not isinstance(st, dict):
        return _default_state()
    st.setdefault('version', 1)
    st.setdefault('slots', list(SLOTS))
    st.setdefault('next_index', 0)
    st.setdefault('disabled', {})
    return st


def _write_state(fh, st: dict) -> None:
    st = dict(st)
    st['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    payload = json.dumps(st, indent=2) + '\n'
    fh.seek(0)
    fh.truncate()
    fh.write(payload)
    fh.flush()
    try:
        os.fsync(fh.fileno())
    except OSError:
        pass


def _active_slots(keys: dict, disabled: dict) -> list:
    out = []
    for s in SLOTS:
        if s in keys and s not in disabled:
            out.append(s)
    return out


def acquire_slot() -> tuple[str, str]:
    """Pick next enabled slot (A→B→A→B). Returns (slot_id, secret). Persists counter under flock."""
    with _MEM_LOCK:
        keys = _read_keys_unlocked()
        STATE_PATH.parent.mkdir(mode=0o700, exist_ok=True)
        # ensure state file exists
        if not STATE_PATH.exists():
            fd, tmp = tempfile.mkstemp(dir=str(STATE_PATH.parent), prefix='state.', text=True)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'w') as f:
                    json.dump(_default_state(), f, indent=2)
                    f.write('\n')
                os.replace(tmp, STATE_PATH)
                os.chmod(STATE_PATH, 0o600)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.unlink(tmp)
                    except FileNotFoundError:
                        pass

        with open(STATE_PATH, 'r+', encoding='utf-8') as fh:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                st = _load_state(fh)
                disabled = dict(st.get('disabled') or {})
                active = _active_slots(keys, disabled)
                if not active:
                    # all disabled — still report clearly; do not invent a key
                    reasons = ','.join(f'{s}:{disabled.get(s)}' for s in SLOTS if s in disabled)
                    raise AisaKeyringError(f'all AISA key slots disabled ({reasons})')
                idx = int(st.get('next_index') or 0) % len(active)
                slot = active[idx]
                st['next_index'] = (idx + 1) % len(active)
                # If some slots disabled, keep next_index within active length
                _write_state(fh, st)
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return slot, keys[slot]


def peek_next_slot() -> str:
    """Read-only: which slot id would be chosen next (no advance)."""
    with _MEM_LOCK:
        keys = _read_keys_unlocked()
        if not STATE_PATH.exists():
            active = _active_slots(keys, {})
            return active[0]
        with open(STATE_PATH, 'r', encoding='utf-8') as fh:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
            try:
                st = _load_state(fh)
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        active = _active_slots(keys, dict(st.get('disabled') or {}))
        if not active:
            raise AisaKeyringError('all AISA key slots disabled')
        idx = int(st.get('next_index') or 0) % len(active)
        return active[idx]


def disable_slot(slot: str, reason_code: str) -> None:
    """Mark slot disabled (e.g. http_401). reason_code must not include secrets."""
    if slot not in SLOTS:
        raise AisaKeyringError(f'unknown slot {slot}')
    # strip anything that could leak
    reason_code = ''.join(c for c in str(reason_code)[:64] if c.isalnum() or c in ('_', '-'))
    with _MEM_LOCK:
        STATE_PATH.parent.mkdir(mode=0o700, exist_ok=True)
        with open(STATE_PATH, 'r+', encoding='utf-8') as fh:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                st = _load_state(fh)
                disabled = dict(st.get('disabled') or {})
                disabled[slot] = reason_code or 'disabled'
                st['disabled'] = disabled
                _write_state(fh, st)
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def slot_ids_configured() -> list:
    with _MEM_LOCK:
        return sorted(_read_keys_unlocked().keys())


def _cli(argv=None):
    """CLI: peek | slots | acquire-file <path> | status
    Never prints secret material. acquire-file writes slot\\nsecret to a mode-0600 file.
    """
    import argparse
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(prog='aisa_keyring', description='AISA A/B keyring (slot ids only on stdout)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('peek', help='print next slot id without advancing')
    sub.add_parser('slots', help='print configured slot ids')
    sub.add_parser('status', help='print next_index and disabled slot ids (no secrets)')
    p_af = sub.add_parser('acquire-file', help='acquire next slot; write slot\\nsecret to 0600 file')
    p_af.add_argument('path')
    args = ap.parse_args(argv)
    if args.cmd == 'peek':
        print(peek_next_slot())
        return 0
    if args.cmd == 'slots':
        print(' '.join(slot_ids_configured()))
        return 0
    if args.cmd == 'status':
        st = _default_state()
        if STATE_PATH.exists():
            with open(STATE_PATH, 'r', encoding='utf-8') as fh:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
                try:
                    st = _load_state(fh)
                finally:
                    if fcntl is not None:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        disabled = sorted((st.get('disabled') or {}).keys())
        print(json.dumps({
            'next_index': int(st.get('next_index') or 0),
            'disabled_slots': disabled,
            'configured_slots': slot_ids_configured(),
            'peek': (peek_next_slot() if slot_ids_configured() else None),
        }, ensure_ascii=False))
        return 0
    if args.cmd == 'acquire-file':
        slot, secret = acquire_slot()
        path = Path(args.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.aisa_acq.', text=True)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(slot + '\n' + secret + '\n')
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
        # stdout: slot only
        print(slot)
        return 0
    return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(_cli())
