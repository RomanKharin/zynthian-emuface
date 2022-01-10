#!/usr/bin/python3
# -*- coding: utf-8 -*-

from collections import _OrderedDictValuesView
import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from time import sleep

from PIL import Image, ImageTk
import Xlib
import Xlib.display

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("emuface_tk")

def stream_reader(out, queue, name):
    for line in iter(out.readline, b""):
        line = line.replace(b"FLUSH\n", b"")
        line = line.replace(b"FLUSH", b"")
        if not line:
            continue
        queue.put(line)
    out.close()


class App:
    def __init__(self):
        self.master = tk.Tk()
        top_info = tk.Label(self.master, text="Zynthian emuface")
        top_info.pack()
        self.top_info = top_info
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.zynth_w = 480
        self.zynth_h = 320

        #frame = tk.Frame(self.master, width=self.zynth_w, 
        #    height=self.zynth_h, container=1
        #)
        #frame.pack()
        self.frame = tk.Canvas(self.master, width=self.zynth_w, 
            height=self.zynth_h)
        self.frame.pack()

        self.process = None
        self.q_stdout = None
        self.q_stderr = None

        self.zynth_xid = None
        self.zynth_win = None
        self.zynth_parent_xid = None

        try:
            envs = {k:v for k, v in os.environ.items()}
            emubin = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 
                "emubin"
            )
            old_path = os.environ.get("PATH")
            envs["PATH"] = emubin + (
                os.pathsep + old_path
            ) if old_path else "" 
            old_path = os.environ.get("PYTHONPATH")
            envs["PYTHONPATH"] = emubin + (
                os.pathsep + old_path
            ) if old_path else "" 
            
            self.process = subprocess.Popen(
                #["python", "transient.py", str(self.master.winfo_id())],
                #["xterm", "-into", str(self.master.winfo_id())],
                ["./zynthian_gui_emu.sh", str(self.frame.winfo_id())],
                bufsize=0,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                env=envs
            )
        except Exception:
            logger.exception("Can't start subprocess")
            self.process = None

        if self.process:
            top_info.config(text="Zynthian PID=%s" % self.process.pid)
            qo = queue.Queue()
            to = threading.Thread(
                target=stream_reader,
                args=(self.process.stdout, qo, "STDOUT"),
            )
            to.daemon = True
            to.start()

            qe = queue.Queue()
            te = threading.Thread(
                target=stream_reader,
                args=(self.process.stderr, qe, "STDERR"),
            )
            te.daemon = True
            te.start()

            self.thread_stdout = to
            self.q_stdout = qo
            self.thread_stderr = te
            self.q_stderr = qe

            self.on_after()

        if self.process:
            print("Read output for %s" % self.process.pid)
        else:
            print("No subprocess")

    def on_closing(self):
        if self.process:
            self.top_info.config(text="Closing PID=%s" % self.process.pid)
            os.kill(self.process.pid, signal.SIGKILL)
        #self.master.reparent()
        self.master.destroy()

    def on_after(self):
        try:

            if self.q_stdout:
                try:
                    lines = b""
                    while not self.q_stdout.empty():
                        lines += self.q_stdout.get_nowait()
                except queue.Empty:
                    pass
                if lines:
                    lines = lines.decode("utf-8")
                    for line in lines.split("\n"):
                        if line.startswith("Zynthian GUI XID:"):
                            self.zynth_xid = line[17:].strip()
                            self.update_zynth_geometry()
                        elif line.startswith("Parent XID:"):
                            self.zynth_parent_xid = line[11:].strip()
                        if line:
                            logger.info(line)

            if self.q_stderr:
                try:
                    lines = b""
                    while not self.q_stderr.empty():
                        lines += self.q_stderr.get_nowait()
                except queue.Empty:
                    pass
                if lines:
                    lines = lines.decode("utf-8")
                    for line in lines.split("\n"):
                        if line:
                            if line[:5] == "INFO:":
                                logger.info(line[5:])
                            elif line[:6] == "ERROR:":
                                logger.error(line[6:])
                            elif line[:6] == "DEBUG:":
                                logger.debug(line[6:])
                            else:
                                logger.error(line)

        except Exception:
            logger.exception("Error on_after")

        try:
            if self.zynth_win:
                raw = self.zynth_win.get_image(
                    0, 0, self.zynth_w, self.zynth_h, Xlib.X.ZPixmap, 
                    0xffffffff
                )
                image = Image.frombytes(
                    "RGB", (self.zynth_w, self.zynth_h), 
                    raw.data, "raw", "BGRX"
                )
                self.zynth_img = ImageTk.PhotoImage(image, size=image.size)
                self.frame.delete()
                self.zynth_imgs = self.frame.create_image(
                    0, 0, anchor=tk.NW, image=self.zynth_img
                )
        except Xlib.error.BadMatch:
            # just wait little more
            pass
        except Exception:
            logger.exception("Error capture")


        self.master.after(330, self.on_after)

    def update_zynth_geometry(self):
        d = Xlib.display.Display()
        self.zynth_win = d.create_resource_object('window', 
            int(self.zynth_xid, 10))
        self.zynth_win.query_tree().parent

if __name__ == "__main__":
    app = App()
    app.master.mainloop()
