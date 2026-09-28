# -*- coding: utf-8 -*-
"""Where a batch's files live (Tucker, 2026-09-28). Only the latest primary outputs sit at the top of a batch folder:
the workbook (.xlsx), the KMZ and the two memos. Machine files (sites.csv, provenance.csv, run.json,
broker_summary.csv, ratings.csv) go in 'Supporting outputs/'. A primary output that is replaced moves to 'Archive/'
first, named '<name> <modified YYYY-MM-DD HHMM>'. input/ (session work) and figures/ (exhibits) stay as they are.

    support(b, 'sites.csv')              -> the path to read (a batch from before the folders still reads from the top)
    support(b, 'sites.csv', write=True)  -> the path to write; an old copy at the top moves to Archive/
    publish(b, 'X.docx', d.save)         -> writes a primary output through write(path); the previous version, and any
                                            '(new N)' copy, moves to Archive/ unless the content is unchanged. When the
                                            file is open (locked), writes '<name> (new).<ext>' beside it and says so.
"""
import os, re, time, zipfile

SUPPORT, ARCHIVE = 'Supporting outputs', 'Archive'


def support(b, name, write=False):
    new, top = os.path.join(b, SUPPORT, name), os.path.join(b, name)
    if write:
        os.makedirs(os.path.dirname(new), exist_ok=True)
        if os.path.exists(top):
            archive(top)
        return new
    return top if not os.path.exists(new) and os.path.exists(top) else new


def archive(path):
    """Move a file into its batch's Archive/ as '<stem> <modified YYYY-MM-DD HHMM><ext>'. Returns the new path, or None
    when the file is open (locked)."""
    b = os.path.dirname(path)
    stem, ext = os.path.splitext(os.path.basename(path))
    stem = re.sub(r' \(new(?: \d+)?\)$', '', stem)
    os.makedirs(os.path.join(b, ARCHIVE), exist_ok=True)
    base = f"{stem} {time.strftime('%Y-%m-%d %H%M', time.localtime(os.path.getmtime(path)))}"
    dest, i = os.path.join(b, ARCHIVE, base + ext), 2
    while os.path.exists(dest):
        dest, i = os.path.join(b, ARCHIVE, f'{base} ({i}){ext}'), i + 1
    try:
        os.rename(path, dest)
    except PermissionError:
        return None
    return dest


def _content(path):
    """What counts as a change: every zip member except the save-time properties (docx, xlsx, kmz), or the bytes."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            return {n: z.read(n) for n in z.namelist() if n != 'docProps/core.xml'}
    return open(path, 'rb').read()


def publish(b, name, write):
    final = os.path.join(b, name)
    stem, ext = os.path.splitext(name)
    tmp = os.path.join(b, f'~writing {stem}{ext}')
    write(tmp)
    copies = [os.path.join(b, f'{stem} (new{s}){ext}') for s in [''] + [f' {i}' for i in range(2, 10)]]
    for c in copies:
        if os.path.exists(c):
            archive(c)
    if os.path.exists(final) and _content(final) == _content(tmp):
        os.remove(tmp)
        return final
    if os.path.exists(final) and archive(final) is None:
        alt = next(c for c in copies if not os.path.exists(c))
        os.replace(tmp, alt)
        print(f'  {name} is open (locked): wrote {os.path.basename(alt)} instead; close it and rerun to replace it')
        return alt
    os.replace(tmp, final)
    return final
