EOFError: This app has encountered an error. The original error message is redacted to prevent data leaks. Full error details have been recorded in the logs (if you're on Streamlit Cloud, click on 'Manage app' in the lower right of your app).
Traceback:
File "/mount/src/dj-tracks/streamlit_app.py", line 44, in <module>
    ensure_ffmpeg()
File "/mount/src/dj-tracks/streamlit_app.py", line 35, in ensure_ffmpeg
    for member in tar.getmembers():
                  ^^^^^^^^^^^^^^^^
File "/usr/local/lib/python3.12/tarfile.py", line 2027, in getmembers
    self._load()        # all members, we first have to
    ^^^^^^^^^^^^
File "/usr/local/lib/python3.12/tarfile.py", line 2729, in _load
    while self.next() is not None:
          ^^^^^^^^^^^
File "/usr/local/lib/python3.12/tarfile.py", line 2635, in next
    self.fileobj.seek(self.offset - 1)
File "/usr/local/lib/python3.12/lzma.py", line 261, in seek
    return self._buffer.seek(offset, whence)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/usr/local/lib/python3.12/_compression.py", line 153, in seek
    data = self.read(min(io.DEFAULT_BUFFER_SIZE, offset))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/usr/local/lib/python3.12/_compression.py", line 99, in read
    raise EOFError("Compressed file ended before the "
