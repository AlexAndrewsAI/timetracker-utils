from pathlib import Path

# Fix _serialise_lists: empty lists -> "" not "[]"
p = Path('/root/timetracker-utils/timetracker_utils/database.py')
src = p.read_text()
old = '''            df[col] = df[col].apply(
                lambda x: json.dumps(x) if isinstance(x, list) else ("" if _is_blank(x) else str(x))
            )
        return df


def _deserialise_lists'''
new = '''            df[col] = df[col].apply(
                lambda x: json.dumps(x) if isinstance(x, list) and len(x) > 0 else ("" if _is_blank(x) else str(x))
            )
        return df


def _deserialise_lists'''
if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print('patched _serialise_lists')
else:
    print('old text not found')
