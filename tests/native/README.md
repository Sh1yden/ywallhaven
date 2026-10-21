# Native tests

This directory contains tests that must run on a real target OS. They
exist for behaviour that cannot be verified reliably with mocks:

- real Win32 API calls (`ctypes.windll`);
- POSIX executable bits and `chmod`;
- `/proc` process discovery;
- helper replacement and restart flags.

Rules:

- A native test must have both the `native` marker and a platform
  marker (`native_linux`, `native_win` or, later, `native_android`).
- A native module must skip itself on the wrong OS.
- Never patch `sys.platform` in a native test: the point is to test the
  real environment.
- Never change the user's wallpaper, trigger UAC, or write outside
  `tmp_path`.
- Business logic belongs to the shared suite; do not duplicate it here.
