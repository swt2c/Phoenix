#!/usr/bin/env python
"""
One-off harness for trying to reproduce macOS-only issues on a GitHub runner,
using released wxPython wheels and the matching demo folder:

  #2966  PyShell shows no prompt and won't accept typing (4.3.x)
  #2965  HyperTreeList demo folder icons drawn wrong
  #2840  GraphicsContext gradients rendered as a solid colour (macOS 26)

Usage: repro.py all | env | pyshell | hypertreelist | gradient | gradientdemo

REPRO_DEMO is the wxPython demo folder, REPRO_OUT is where the screenshots
and summary.txt / details.txt are written.
"""

import os
import platform
import subprocess
import sys
import traceback

OUT = os.path.abspath(os.environ.get('REPRO_OUT', 'repro-out'))
DEMO = os.path.abspath(os.environ.get('REPRO_DEMO', 'demo'))
SCENARIOS = ['pyshell', 'hypertreelist', 'gradient', 'gradientdemo']
SETTLE_MS = 3000


def _write(fname, msg):
    with open(os.path.join(OUT, fname), 'a') as f:
        f.write(msg + '\n')


def log(*args):
    """Important result: goes to stdout, summary.txt and details.txt."""
    msg = ' '.join(str(a) for a in args)
    print(msg, flush=True)
    _write('summary.txt', msg)
    _write('details.txt', msg)


def detail(*args):
    """Verbose diagnostics: stdout and details.txt only."""
    msg = ' '.join(str(a) for a in args)
    print(msg, flush=True)
    _write('details.txt', msg)


def run_cmd(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f'<{cmd[0]} failed: {e}>'


def finish(code=0):
    sys.stdout.flush()
    sys.stderr.flush()
    # Skip wx/AppKit teardown; we only care about what was already logged.
    os._exit(code)


#---------------------------------------------------------------------------
# Environment

def macho_versions(path):
    """minos/sdk load commands of a Mach-O, which drive AppKit's
    linked-on-or-after compatibility behaviour."""
    lines = run_cmd(['otool', '-l', path]).splitlines()
    found = []
    for i, line in enumerate(lines):
        if 'LC_BUILD_VERSION' in line or 'LC_VERSION_MIN_MACOSX' in line:
            fields = [l.strip() for l in lines[i + 1:i + 6]
                      if l.strip().split(' ')[0] in ('minos', 'sdk', 'version')]
            found.append(line.strip().split()[-1] + ': ' + ', '.join(fields))
    return found or ['<no version load command found>']


def run_env():
    import wx
    log('== env')
    log('macOS', platform.mac_ver()[0], platform.machine())
    log('Python', sys.version.replace('\n', ' '))
    log('wx', wx.version())
    log('sys.executable', sys.executable)
    binaries = {
        'sys.executable (real)': os.path.realpath(sys.executable),
        'framework Python.app': os.path.join(
            sys.base_prefix, 'Resources/Python.app/Contents/MacOS/Python'),
        'wx._core': wx._core.__file__,
    }
    for label, path in binaries.items():
        if os.path.exists(path):
            for v in macho_versions(path):
                log(f'  {label}: {v}  [{path}]')
    detail(run_cmd(['sw_vers']))
    detail(run_cmd(['system_profiler', 'SPDisplaysDataType']))
    detail('AppleInterfaceStyle:', run_cmd(['defaults', 'read', '-g', 'AppleInterfaceStyle']))
    detail(run_cmd([sys.executable, '-m', 'pip', 'list']))


#---------------------------------------------------------------------------
# GUI helpers

def nswindow_for(win):
    import AppKit
    import objc
    obj = objc.objc_object(c_void_p=win.GetHandle())
    if obj.isKindOfClass_(AppKit.NSWindow):
        return obj
    return obj.window()


def activate_app():
    try:
        import AppKit
        app = AppKit.NSApplication.sharedApplication()
        if app.respondsToSelector_('activate'):
            app.activate()
        app.activateIgnoringOtherApps_(True)
    except Exception as e:
        detail('activate failed:', e)


def capture(win, name):
    """
    Grab win's top-level window three ways:
      -view.png    AppKit renders the content view into a bitmap (no
                   screen-recording permission needed)
      -window.png  screencapture of just that window (what the compositor shows)
      -screen.png  full screen
    Returns info needed to map wx coordinates onto the PNGs.
    """
    import AppKit
    win.Update()
    nswin = nswindow_for(win)
    info = {'nswin': nswin}

    cv = nswin.contentView()
    rect = cv.bounds()
    rep = cv.bitmapImageRepForCachingDisplayInRect_(rect)
    cv.cacheDisplayInRect_toBitmapImageRep_(rect, rep)
    data = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    path = os.path.join(OUT, f'{name}-view.png')
    data.writeToFile_atomically_(path, True)
    info['view'] = path
    info['view_scale'] = rep.pixelsWide() / rect.size.width

    path = os.path.join(OUT, f'{name}-window.png')
    out = run_cmd(['screencapture', '-x', '-o', f'-l{nswin.windowNumber()}', path])
    if os.path.exists(path):
        info['window'] = path
        info['window_scale'] = load_image(path).GetWidth() / nswin.frame().size.width
    else:
        log(f'  screencapture -l failed: {out}')

    path = os.path.join(OUT, f'{name}-screen.png')
    out = run_cmd(['screencapture', '-x', path])
    if not os.path.exists(path):
        log(f'  screencapture (full screen) failed: {out}')

    detail(f'  captured {name}: view scale {info["view_scale"]}, '
           f'window scale {info.get("window_scale")}')
    return info


_images = {}


def load_image(path):
    import wx
    if path not in _images:
        _images[path] = wx.Image(path)
    return _images[path]


def pixel(img, x, y):
    x, y = int(x), int(y)
    if not img.IsOk() or not (0 <= x < img.GetWidth() and 0 <= y < img.GetHeight()):
        return None
    return (img.GetRed(x, y), img.GetGreen(x, y), img.GetBlue(x, y))


def log_scale_info(win):
    import wx
    try:
        disp = wx.Display(0).GetScaleFactor()
    except Exception as e:
        disp = e
    log(f'  display scale {disp}, content scale {win.GetContentScaleFactor()}, '
        f'DPI scale {win.GetDPIScaleFactor()}, '
        f'dark={wx.SystemSettings.GetAppearance().IsDark()}')


def run_demo(module_name, on_ready):
    """Run a demo module through the demo's run.py, then call on_ready(app)
    once things have had time to settle."""
    import wx
    sys.path.insert(0, DEMO)
    import run
    run.assertMode = wx.APP_ASSERT_LOG

    orig_oninit = run.RunDemoApp.OnInit

    def OnInit(self):
        ok = orig_oninit(self)
        activate_app()
        wx.CallLater(SETTLE_MS, guarded, on_ready, self)
        return ok

    run.RunDemoApp.OnInit = OnInit
    run.main(['run.py', module_name])
    log('  main loop exited before the scenario finished')
    finish(2)


def guarded(func, *args):
    try:
        func(*args)
    except Exception:
        log('  EXCEPTION:\n' + traceback.format_exc())
        finish(1)


def later(ms, func, *args):
    import wx
    wx.CallLater(ms, guarded, func, *args)


#---------------------------------------------------------------------------
# #2966 PyShell

def shell_state(shell, label):
    import wx
    pos = shell.GetCurrentPos()
    log(f'  [{label}] length={shell.GetLength()} lines={shell.GetLineCount()} '
        f'firstVisible={shell.GetFirstVisibleLine()} linesOnScreen={shell.LinesOnScreen()} '
        f'curPos={pos} promptPosEnd={shell.promptPosEnd} '
        f'caretPoint={tuple(shell.PointFromPosition(pos))} xOffset={shell.GetXOffset()} '
        f'vscroll={shell.GetScrollPos(wx.VERTICAL)}/{shell.GetScrollRange(wx.VERTICAL)} '
        f'clientSize={tuple(shell.GetClientSize())} textHeight={shell.TextHeight(0)} '
        f'zoom={shell.GetZoom()} focus={shell.HasFocus()}')
    log(f'  [{label}] last lines: {shell.GetText().splitlines()[-3:]!r}')
    detail(f'  [{label}] full text: {shell.GetText()!r}')


def run_pyshell():
    import wx

    def ready(app):
        shell = app.window
        log_scale_info(shell)
        shell_state(shell, 'initial')
        app.initial_text = shell.GetText()
        has_prompt = shell.GetText().rstrip().endswith('>>>')
        log(f'  prompt present at end of text: {has_prompt}')
        capture(shell, 'pyshell-initial')

        app.frame.Raise()
        activate_app()
        shell.SetFocus()
        sim = wx.UIActionSimulator()
        sim.Text(b'6*7')
        sim.Char(wx.WXK_RETURN)
        later(2000, typed, app)

    def typed(app):
        shell = app.window
        shell_state(shell, 'after typing 6*7<Enter>')
        text = shell.GetText()
        if text.startswith(app.initial_text):
            text = text[len(app.initial_text):]
        log(f'  new text after typing: {text!r}')
        log(f'  typed input echoed: {"6*7" in text}, evaluated to 42: {"42" in text}')
        capture(shell, 'pyshell-typed')

        # Control: does the simulator reach a plain TextCtrl on this runner?
        frame = wx.Frame(None, title='UIActionSimulator control', pos=(900, 100), size=(300, 100))
        tc = wx.TextCtrl(frame)
        frame.Show()
        frame.Raise()
        activate_app()
        tc.SetFocus()
        later(500, control_type, app, tc)

    def control_type(app, tc):
        wx.UIActionSimulator().Text(b'abc')
        later(1000, control_check, app, tc)

    def control_check(app, tc):
        log(f'  control TextCtrl value after simulated typing: {tc.GetValue()!r} '
            f'(if empty, simulated input does not work here and the typing test is inconclusive)')
        finish(0)

    run_demo('PyShell.py', ready)


#---------------------------------------------------------------------------
# #2965 HyperTreeList

def run_hypertreelist():
    import wx

    def ready(app):
        app.window.OnButton(None)
        activate_app()
        later(SETTLE_MS, shoot, app)

    def shoot(app):
        demo = app.window.win
        tree = demo.tree
        log_scale_info(tree)
        ArtIDs = sys.modules['HyperTreeList'].ArtIDs[1:-1]
        il = tree.GetImageList()
        log(f'  tree image list: count={il.GetImageCount()} size(0)={il.GetSize(0)}')

        bad = []
        sheet = wx.Bitmap(len(ArtIDs) * 40 + 10, 110)
        dc = wx.MemoryDC(sheet)
        dc.SetBackground(wx.WHITE_BRUSH)
        dc.Clear()
        for i, name in enumerate(ArtIDs):
            art_id = getattr(wx, name.split('.', 1)[1])
            parts = []
            x = 10 + i * 40
            for row, client in enumerate(['ART_TOOLBAR', 'ART_OTHER']):
                bmp = wx.ArtProvider.GetBitmap(art_id, getattr(wx, client), (16, 16))
                bundle = wx.ArtProvider.GetBitmapBundle(art_id, getattr(wx, client))
                size = tuple(bmp.GetSize())
                parts.append(f'{client}={size[0]}x{size[1]}@{bmp.GetScaleFactor()} '
                             f'bundleDefault={tuple(bundle.GetDefaultSize())}')
                if size != (16, 16) and client == 'ART_TOOLBAR':
                    bad.append(f'{i}:{name}={size[0]}x{size[1]}')
                if bmp.IsOk():
                    dc.DrawBitmap(bmp, x, 5 + row * 35, True)
            il_size = il.GetSize(i)
            parts.append(f'imagelist={il_size} bmp={tuple(il.GetBitmap(i).GetSize())}')
            il.Draw(i, dc, x, 75, wx.IMAGELIST_DRAW_TRANSPARENT)
            detail(f'  {i:2d} {name:24s} ' + '  '.join(parts))
        dc.SelectObject(wx.NullBitmap)
        path = os.path.join(OUT, 'hypertreelist-artsheet.png')
        sheet.SaveFile(path, wx.BITMAP_TYPE_PNG)
        log('  art sheet rows: ART_TOOLBAR bitmap, ART_OTHER bitmap, image list Draw()')
        log(f'  ART_TOOLBAR bitmaps that are not 16x16: {bad or "none"}')
        log(f'  index 24 (used for collapsed items) = {ArtIDs[24]}, '
            f'index 13 (expanded) = {ArtIDs[13]}')
        capture(demo, 'hypertreelist')
        finish(0)

    run_demo('HyperTreeList.py', ready)


#---------------------------------------------------------------------------
# #2840 gradients

GRADIENTS = ['linear', 'linear_stops', 'linear_rounded', 'radial', 'dc_gradientfill']
GRAD_SIZE = (400, 40)


def draw_gradient(dc, kind, w, h):
    import wx
    if kind == 'dc_gradientfill':
        dc.GradientFillLinear(wx.Rect(0, 0, w, h), wx.RED, wx.BLUE, wx.RIGHT)
        return
    gc = wx.GraphicsContext.Create(dc)
    if kind == 'linear':
        brush = gc.CreateLinearGradientBrush(0, 0, w, 0, wx.RED, wx.BLUE)
    elif kind in ('linear_stops', 'linear_rounded'):
        stops = wx.GraphicsGradientStops(wx.RED, wx.BLUE)
        stops.Add(wx.GraphicsGradientStop(wx.GREEN, 0.5))
        brush = gc.CreateLinearGradientBrush(0, 0, w, 0, stops)
    else:
        brush = gc.CreateRadialGradientBrush(w / 2, h / 2, w / 2, h / 2, w / 2,
                                             wx.WHITE, wx.BLACK)
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(brush)
    if kind == 'linear_rounded':
        gc.DrawRoundedRectangle(0, 0, w, h, 3)
    else:
        gc.DrawRectangle(0, 0, w, h)


def sample_points(kind, w, h):
    if kind == 'radial':
        return (w / 2, h / 2), (8, h / 2)
    return (5, h / 2), (w - 6, h / 2)


def verdict(a, b):
    if a is None or b is None:
        return f'n/a ({a} vs {b})'
    diff = max(abs(x - y) for x, y in zip(a, b))
    return f'{"gradient" if diff >= 60 else "SOLID"} ({a} vs {b})'


def run_gradient():
    import wx

    class GradPanel(wx.Panel):
        def __init__(self, parent, kind):
            super().__init__(parent, size=GRAD_SIZE)
            self.kind = kind
            self.SetMinSize(GRAD_SIZE)
            self.Bind(wx.EVT_PAINT, self.OnPaint)

        def OnPaint(self, evt):
            dc = wx.PaintDC(self)
            w, h = self.GetClientSize()
            draw_gradient(dc, self.kind, w, h)

    app = wx.App()
    log(f'  renderer: {wx.GraphicsRenderer.GetDefaultRenderer().GetName()}')
    frame = wx.Frame(None, title='Gradient repro', pos=(50, 50))
    bg = wx.Panel(frame)
    sizer = wx.BoxSizer(wx.VERTICAL)
    panels = {}
    for kind in GRADIENTS:
        sizer.Add(wx.StaticText(bg, label=kind), 0, wx.LEFT | wx.TOP, 8)
        panels[kind] = GradPanel(bg, kind)
        sizer.Add(panels[kind], 0, wx.ALL, 8)
    bg.SetSizer(sizer)
    frame.SetClientSize(sizer.GetMinSize())
    frame.Show()
    activate_app()

    def shoot():
        log_scale_info(frame)
        w, h = GRAD_SIZE
        for kind in GRADIENTS:
            bmp = wx.Bitmap(w, h)
            dc = wx.MemoryDC(bmp)
            dc.SetBackground(wx.Brush(wx.Colour(128, 128, 128)))
            dc.Clear()
            draw_gradient(dc, kind, w, h)
            dc.SelectObject(wx.NullBitmap)
            bmp.SaveFile(os.path.join(OUT, f'gradient-offscreen-{kind}.png'), wx.BITMAP_TYPE_PNG)
            img = bmp.ConvertToImage()
            p1, p2 = sample_points(kind, w, h)
            log(f'  offscreen {kind:16s}: {verdict(pixel(img, *p1), pixel(img, *p2))}')

        info = capture(frame, 'gradient')
        frame_pos = frame.GetScreenPosition()
        for kind, panel in panels.items():
            pw, ph = panel.GetClientSize()
            p1, p2 = sample_points(kind, pw, ph)
            origin = panel.ClientToScreen(wx.Point(0, 0))
            client = frame.ScreenToClient(origin)
            s = info['view_scale']
            img = load_image(info['view'])
            v = verdict(pixel(img, (client.x + p1[0]) * s, (client.y + p1[1]) * s),
                        pixel(img, (client.x + p2[0]) * s, (client.y + p2[1]) * s))
            log(f'  view      {kind:16s}: {v}')
            if 'window' in info:
                s = info['window_scale']
                ox, oy = origin.x - frame_pos.x, origin.y - frame_pos.y
                img = load_image(info['window'])
                v = verdict(pixel(img, (ox + p1[0]) * s, (oy + p1[1]) * s),
                            pixel(img, (ox + p2[0]) * s, (oy + p2[1]) * s))
                log(f'  window    {kind:16s}: {v}')
        finish(0)

    later(SETTLE_MS, shoot)
    app.MainLoop()
    finish(2)


def run_gradientdemo():
    def ready(app):
        log_scale_info(app.frame)
        capture(app.frame, 'gradientdemo')
        finish(0)

    run_demo('GraphicsGradient.py', ready)


#---------------------------------------------------------------------------

def run_all():
    run_env()
    failed = []
    for name in SCENARIOS:
        try:
            rc = subprocess.run([sys.executable, os.path.abspath(__file__), name],
                                timeout=180).returncode
        except subprocess.TimeoutExpired:
            rc = 'timeout'
            log(f'== {name}: TIMED OUT')
        if rc != 0:
            failed.append(f'{name} ({rc})')
    log(f'== harness failures: {failed or "none"}')
    return 1 if failed else 0


def main():
    os.makedirs(OUT, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what == 'all':
        return run_all()
    if what == 'env':
        return run_env()
    import wx
    log(f'== {what} (wx {wx.version()}, Python {platform.python_version()}, '
        f'macOS {platform.mac_ver()[0]})')
    guarded(globals()['run_' + what])
    return 0


if __name__ == '__main__':
    sys.exit(main())
