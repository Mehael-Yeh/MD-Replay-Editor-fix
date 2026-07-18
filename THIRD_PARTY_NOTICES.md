# Third-party notices

MD-Replay-Editor-fix contains, adapts, bundles, or refers to third-party
software. Each component remains subject to its own license.

## Component overview

| Component | How it is used | License | Included in release EXE |
| --- | --- | --- | --- |
| [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor) | Original replay capture and response-replacement implementation patterns | MIT | Adapted implementation |
| [Frida](https://github.com/frida/frida) | Process attachment and runtime instrumentation | wxWindows Library Licence 3.1 | Yes |
| [frida-il2cpp-bridge](https://github.com/vfsfitvnm/frida-il2cpp-bridge) | IL2CPP runtime access from the injected agent | MIT | Yes |
| [Python](https://www.python.org/) | Application runtime | PSF License | Yes |
| [Tcl/Tk](https://www.tcl.tk/) | Tkinter graphical interface runtime | Tcl/Tk License | Yes |
| [PyInstaller](https://pyinstaller.org/) | Builds the portable executable and supplies its bootloader | GPL 2.0 or later with the PyInstaller bootloader exception | Bootloader only |
| [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) | Technical reference for Master Duel networking and replay management | MIT | No |

The JavaScript agent is compiled from the dependency versions recorded in
`agent/package-lock.json`. That lockfile is the authoritative inventory for
transitive npm packages and their versions.

## crazydoomy/MD-Replay-Editor

Copyright (c) 2022 crazydoomy

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Upstream license:
<https://github.com/crazydoomy/MD-Replay-Editor/blob/main/LICENSE>

## frida-il2cpp-bridge

Copyright (c) 2021-2026 vfsfitvnm

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Upstream license:
<https://github.com/vfsfitvnm/frida-il2cpp-bridge/blob/master/LICENSE>

## Frida

Frida is distributed under the wxWindows Library Licence, Version 3.1.

Copyright (c) 1998-2005 Julian Smart, Robert Roebling et al

Everyone is permitted to copy and distribute verbatim copies of this licence
document, but changing it is not allowed.

### WXWINDOWS LIBRARY LICENCE

#### TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

This library is free software; you can redistribute it and/or modify it under
the terms of the GNU Library General Public Licence as published by the Free
Software Foundation; either version 2 of the Licence, or (at your option) any
later version.

This library is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU Library General Public Licence for more
details.

You should have received a copy of the GNU Library General Public Licence
along with this software, usually in a file named COPYING.LIB. If not, write
to the Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor,
Boston, MA 02110-1301 USA.

#### EXCEPTION NOTICE

1. As a special exception, the copyright holders of this library give
   permission for additional uses of the text contained in this release of
   the library as licenced under the wxWindows Library Licence, applying
   either version 3.1 of the Licence, or (at your option) any later version of
   the Licence as published by the copyright holders of version 3.1 of the
   Licence document.
2. The exception is that you may use, copy, link, modify and distribute under
   your own terms, binary object code versions of works based on the Library.
3. If you copy code from files distributed under the terms of the GNU General
   Public Licence or the GNU Library General Public Licence into a copy of
   this library, as this licence permits, the exception does not apply to the
   code that you add in this way. To avoid misleading anyone as to the status
   of such modified files, you must delete this exception notice from such
   code and/or adjust the licensing conditions notice accordingly.
4. If you write modifications of your own for this library, it is your choice
   whether to permit this exception to apply to your modifications. If you do
   not wish that, you must delete the exception notice from such code and/or
   adjust the licensing conditions notice accordingly.

Upstream license:
<https://github.com/frida/frida/blob/main/COPYING>

## Other bundled runtimes and build components

- Python license: <https://docs.python.org/3/license.html>
- Tcl/Tk license terms: <https://www.tcl.tk/software/tcltk/license.html>
- PyInstaller license and bootloader exception:
  <https://pyinstaller.org/en/stable/license.html>

PyInstaller's special exception permits distribution of applications produced
with its bootloader under the application's chosen license.

## YgoMaster reference

YgoMaster was studied as a technical reference. No YgoMaster executable,
server, source file, or data asset is distributed by MD-Replay-Editor-fix.

Upstream project and license:
<https://github.com/pixeltris/YgoMaster>

## Trademarks

Yu-Gi-Oh!, Master Duel, Steam, and other product names belong to their
respective owners. Their mention identifies compatibility only and does not
imply endorsement or affiliation.
