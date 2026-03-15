import os
import random
import sys
import time
import tkinter as tk
from tkinter import messagebox

try:
    import sounddevice as sd  # type: ignore
    import numpy as np  # type: ignore

    MIC_AVAILABLE = True
except Exception:
    sd = None
    np = None
    MIC_AVAILABLE = False

def _load_png_image(path):
    """Load a PNG image for Tkinter display."""
    try:
        return tk.PhotoImage(file=path)
    except Exception:
        try:
            from PIL import Image, ImageTk  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Failed to load PNG with Tkinter. Install Pillow or use a supported PNG."
            ) from exc
        img = Image.open(path)
        return ImageTk.PhotoImage(img)


def _composite_png_images(base_path, overlay_path):
    """Composite overlay onto base using alpha (requires Pillow)."""
    try:
        from PIL import Image, ImageTk  # type: ignore
    except Exception:
        return None
    base = Image.open(base_path).convert("RGBA")
    overlay = Image.open(overlay_path).convert("RGBA")
    if overlay.size != base.size:
        # Keep original top-left alignment when sizes differ.
        composed = base.copy()
        composed.paste(overlay, (0, 0), overlay)
    else:
        composed = Image.alpha_composite(base, overlay)
    return ImageTk.PhotoImage(composed)


def main():
    root = tk.Tk()
    root.title("Pixel Char")

    window_ref = {
        "img_window": None,
        "img_label": None,
        "overlay_label": None,
        "img_objs": None,
        "img_index": 0,
        "after_id": None,
        "blink_after_id": None,
        "blink_hold_after_id": None,
        "talking_after_id": None,
        "talking_show_initial": True,
        "talking_base": None,
        "talking_initial_mouth_open": False,
        "mic_stream": None,
        "mic_poll_after_id": None,
        "mic_level": 0.0,
        "mic_threshold": 0.02,
        "mic_talking_active": False,
        "mic_below_since": None,
        "blink_after_talking_id": None,
        "talking_delay_update_id": None,
        "blink_running": False,
        "happy_active": False,
        "happy_after_id": None,
        "happy_base_images": None,
        "happy_overlay_images": None,
        "happy_base_index": 0,
        "happy_overlay_index": 0,
        "sad_active": False,
        "sad_after_id": None,
        "sad_base_images": None,
        "sad_overlay_images": None,
        "sad_base_index": 0,
        "sad_overlay_index": 0,
    }

    delay_var = tk.StringVar(value="500")
    talking_delay_var = tk.StringVar(value="500")
    talking_min_delay_var = tk.StringVar(value="150")
    talking_max_delay_var = tk.StringVar(value="350")
    update_rand_min_var = tk.StringVar(value="1")
    update_rand_max_var = tk.StringVar(value="3")
    eyes_var = tk.StringVar(value="EO_")
    mouth_var = tk.BooleanVar(value=False)
    debug_var = tk.BooleanVar(value=False)
    talking_var = tk.BooleanVar(value=False)
    blink_var = tk.StringVar(value="")
    mic_var = tk.StringVar(value="")
    mic_threshold_var = tk.StringVar(value="0.80")
    mic_release_var = tk.StringVar(value="350")
    mic_status_var = tk.StringVar(value="Mic: --")
    blink_after_talking_var = tk.BooleanVar(value=False)
    blink_after_min_var = tk.StringVar(value="2")
    blink_after_max_var = tk.StringVar(value="6")

    blink_options = {
        "EO: EC -> EO": "EO_1",
        "EO: EM -> EC -> EO": "EO_2",
        "EO: EM (1s) -> EO": "EO_3",
        "EO: EM (2-8s) -> EO": "EO_4",
        "EM: EC -> EM": "EM_5",
        "EM: EC (2s) -> EM": "EM_6",
    }

    def _get_delay_ms():
        raw = delay_var.get().strip()
        try:
            delay = int(float(raw))
        except ValueError:
            messagebox.showerror("Invalid Delay", "Enter a numeric delay in milliseconds.")
            return None
        if delay < 1:
            messagebox.showerror("Invalid Delay", "Delay must be at least 1 ms.")
            return None
        return delay

    def _cancel_animation():
        if window_ref["after_id"] is not None:
            try:
                root.after_cancel(window_ref["after_id"])
            except Exception:
                pass
            window_ref["after_id"] = None

    def _cancel_blink():
        if window_ref["blink_after_id"] is not None:
            try:
                root.after_cancel(window_ref["blink_after_id"])
            except Exception:
                pass
            window_ref["blink_after_id"] = None
        window_ref["blink_running"] = False

    def _cancel_blink_hold():
        if window_ref["blink_hold_after_id"] is not None:
            try:
                root.after_cancel(window_ref["blink_hold_after_id"])
            except Exception:
                pass
            window_ref["blink_hold_after_id"] = None
        window_ref["blink_running"] = False

    def _cancel_talking():
        if window_ref["talking_after_id"] is not None:
            try:
                root.after_cancel(window_ref["talking_after_id"])
            except Exception:
                pass
            window_ref["talking_after_id"] = None

    def _cancel_happy():
        if window_ref["happy_after_id"] is not None:
            try:
                root.after_cancel(window_ref["happy_after_id"])
            except Exception:
                pass
            window_ref["happy_after_id"] = None
        window_ref["happy_active"] = False

    def _cancel_sad():
        if window_ref["sad_after_id"] is not None:
            try:
                root.after_cancel(window_ref["sad_after_id"])
            except Exception:
                pass
            window_ref["sad_after_id"] = None
        window_ref["sad_active"] = False

    def _cancel_mic():
        if window_ref["mic_poll_after_id"] is not None:
            try:
                root.after_cancel(window_ref["mic_poll_after_id"])
            except Exception:
                pass
            window_ref["mic_poll_after_id"] = None
        if window_ref["mic_stream"] is not None:
            try:
                window_ref["mic_stream"].stop()
                window_ref["mic_stream"].close()
            except Exception:
                pass
            window_ref["mic_stream"] = None

    def _cancel_blink_after_talking():
        if window_ref["blink_after_talking_id"] is not None:
            try:
                root.after_cancel(window_ref["blink_after_talking_id"])
            except Exception:
                pass
            window_ref["blink_after_talking_id"] = None

    def _cancel_talking_delay_update():
        if window_ref["talking_delay_update_id"] is not None:
            try:
                root.after_cancel(window_ref["talking_delay_update_id"])
            except Exception:
                pass
            window_ref["talking_delay_update_id"] = None

    def _build_image_path_parts(base, eyes, mouth_open):
        tail = "MO.png" if mouth_open else "MC.png"
        filename = f"{base}{eyes}{tail}"
        return os.path.join(os.path.dirname(__file__), filename)

    def _build_image_path():
        base = "HU_" if window_ref["img_index"] == 0 else "HD_"
        mid = eyes_var.get()
        filename = f"{base}{mid}{'MO.png' if mouth_var.get() else 'MC.png'}"
        return os.path.join(os.path.dirname(__file__), filename)

    def _build_talking_path(mouth_open, base_override=None):
        base = base_override or window_ref["talking_base"] or "HU_"
        mid = eyes_var.get()
        return _build_image_path_parts(base, mid, mouth_open)

    def _load_current_image():
        path = _build_image_path()
        if not os.path.exists(path):
            messagebox.showerror("Missing File", f"Image not found:\n{path}")
            return None
        return _load_png_image(path)

    def _set_image_by_path(path):
        if window_ref["img_label"] is None:
            return False
        if not os.path.exists(path):
            messagebox.showerror("Missing File", f"Image not found:\n{path}")
            return False
        img = _load_png_image(path)
        window_ref["img_label"].configure(image=img)
        window_ref["img_objs"] = [img]
        if window_ref["overlay_label"] is not None:
            window_ref["overlay_label"].configure(image="")
        return True

    def _refresh_image():
        if window_ref["img_label"] is None:
            return
        img = _load_current_image()
        if img is None:
            _cancel_animation()
            _cancel_blink()
            return
        window_ref["img_label"].configure(image=img)
        window_ref["img_objs"] = [img]

    def _animate_next():
        if (
            window_ref["img_window"] is None
            or not window_ref["img_window"].winfo_exists()
            or window_ref["img_label"] is None
            or window_ref["img_objs"] is None
        ):
            _cancel_animation()
            return
        if window_ref["happy_active"]:
            _cancel_animation()
            return
        if window_ref["sad_active"]:
            _cancel_animation()
            return
        if talking_var.get():
            _cancel_animation()
            return

        window_ref["img_index"] = 1 - window_ref["img_index"]
        _refresh_image()

        delay = _get_delay_ms()
        if delay is None:
            return
        window_ref["after_id"] = root.after(delay, _animate_next)

    def _start_animation():
        _cancel_animation()
        if window_ref["happy_active"]:
            return
        if window_ref["sad_active"]:
            return
        if talking_var.get():
            return
        window_ref["img_index"] = 0
        if window_ref["img_label"] is not None:
            _refresh_image()
        delay = _get_delay_ms()
        if delay is None:
            return
        window_ref["after_id"] = root.after(delay, _animate_next)

    def open_image_window():
        if window_ref["img_window"] is not None and window_ref["img_window"].winfo_exists():
            window_ref["img_window"].lift()
            return

        img_window = tk.Toplevel(root)
        img_window.title("Animation")

        img_obj = _load_current_image()
        if img_obj is None:
            img_window.destroy()
            return
        container = tk.Frame(img_window)
        container.pack()
        lbl = tk.Label(container, image=img_obj)
        lbl.pack()
        overlay_lbl = tk.Label(container)
        overlay_lbl.place(x=0, y=0)

        window_ref["img_window"] = img_window
        window_ref["img_label"] = lbl
        window_ref["overlay_label"] = overlay_lbl
        window_ref["img_objs"] = [img_obj]
        window_ref["img_index"] = 0

        def on_close_img():
            _cancel_animation()
            _cancel_blink()
            _cancel_blink_hold()
            _cancel_talking()
            _cancel_blink_after_talking()
            _cancel_talking_delay_update()
            _cancel_happy()
            _cancel_sad()
            if img_window.winfo_exists():
                img_window.destroy()
            window_ref["img_window"] = None
            window_ref["img_label"] = None
            window_ref["overlay_label"] = None
            window_ref["img_objs"] = None

        img_window.protocol("WM_DELETE_WINDOW", on_close_img)
        if window_ref["happy_active"]:
            _start_happy_animation()
            return
        if window_ref["sad_active"]:
            _start_sad_animation()
            return
        if talking_var.get():
            _start_talking()
        else:
            _start_animation()

    def update_animation():
        if window_ref["img_window"] is None or not window_ref["img_window"].winfo_exists():
            messagebox.showinfo("No Window", "Click Start to open the animation window.")
            return
        if talking_var.get():
            _start_talking()
            return
        delay = _get_delay_ms()
        if delay is None:
            return
        _start_animation()

    def _update_blink_menu():
        if eyes_var.get() == "EO_":
            options = ["EO: EC -> EO", "EO: EM -> EC -> EO", "EO: EM (1s) -> EO", "EO: EM (2-8s) -> EO"]
        elif eyes_var.get() == "EM_":
            options = ["EM: EC -> EM", "EM: EC (2s) -> EM"]
        else:
            options = []

        menu = blink_menu["menu"]
        menu.delete(0, "end")
        for opt in options:
            menu.add_command(label=opt, command=lambda v=opt: blink_var.set(v))

        if options:
            if blink_var.get() not in options:
                blink_var.set(options[0])
        else:
            blink_var.set("")

    def _play_blink():
        if window_ref["img_window"] is None or not window_ref["img_window"].winfo_exists():
            messagebox.showinfo("No Window", "Click Start to open the animation window.")
            return

        delay = _get_delay_ms()
        if delay is None:
            return

        name = blink_var.get()
        if not name:
            messagebox.showinfo("No Animation", "Select a blinking animation first.")
            return

        if eyes_var.get() == "EO_" and not name.startswith("EO:"):
            messagebox.showinfo("Wrong Start", "Select an EO animation for Eyes Open.")
            return
        if eyes_var.get() == "EM_" and not name.startswith("EM:"):
            messagebox.showinfo("Wrong Start", "Select an EM animation for Eyes Medium.")
            return

        _run_blink_by_name(name, delay)

    def _run_blink_by_name(name, delay):
        if window_ref["blink_running"]:
            return
        _cancel_blink()

        if name == "EO: EC -> EO":
            sequence = [("EC_", delay), ("EO_", delay)]
        elif name == "EO: EM -> EC -> EO":
            sequence = [("EM_", delay), ("EC_", delay), ("EO_", delay)]
        elif name == "EO: EM (1s) -> EO":
            sequence = [("EM_", 1000), ("EO_", delay)]
        elif name == "EO: EM (2-8s) -> EO":
            hold = random.randint(2000, 8000)
            _cancel_blink_hold()
            eyes_var.set("EM_")
            _refresh_image()
            window_ref["blink_running"] = True
            window_ref["blink_hold_after_id"] = root.after(
                hold,
                lambda: (
                    eyes_var.set("EO_"),
                    _refresh_image(),
                    window_ref.__setitem__("blink_running", False),
                ),
            )
            return
        elif name == "EM: EC -> EM":
            sequence = [("EC_", delay), ("EM_", delay)]
        elif name == "EM: EC (2s) -> EM":
            sequence = [("EC_", 2000), ("EM_", delay)]
        else:
            return

        window_ref["blink_running"] = True

        def step(i):
            if i >= len(sequence):
                window_ref["blink_after_id"] = None
                window_ref["blink_running"] = False
                return
            eyes_var.set(sequence[i][0])
            _refresh_image()
            window_ref["blink_after_id"] = root.after(sequence[i][1], lambda: step(i + 1))

        step(0)

    def _get_blink_after_range_ms():
        try:
            min_s = float(blink_after_min_var.get().strip())
            max_s = float(blink_after_max_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Blink Range", "Enter numeric min/max seconds.")
            return None
        if min_s < 0 or max_s < 0 or max_s < min_s:
            messagebox.showerror(
                "Invalid Blink Range", "Min/Max must be >= 0 and Max >= Min."
            )
            return None
        return int(min_s * 1000), int(max_s * 1000)

    def _schedule_blink_after_talking():
        if not blink_after_talking_var.get():
            _cancel_blink_after_talking()
            return
        rng = _get_blink_after_range_ms()
        if rng is None:
            return
        min_ms, max_ms = rng
        delay_ms = random.randint(min_ms, max_ms)
        _cancel_blink_after_talking()
        window_ref["blink_after_talking_id"] = root.after(
            delay_ms, _run_random_blink
        )

    def _run_random_blink():
        window_ref["blink_after_talking_id"] = None
        if not blink_after_talking_var.get():
            return
        if window_ref["img_window"] is None or not window_ref["img_window"].winfo_exists():
            return
        delay = _get_delay_ms()
        if delay is None:
            return
        if eyes_var.get() == "EO_":
            options = [
                "EO: EC -> EO",
                "EO: EM -> EC -> EO",
                "EO: EM (1s) -> EO",
                "EO: EM (2-8s) -> EO",
            ]
        elif eyes_var.get() == "EM_":
            options = ["EM: EC -> EM", "EM: EC (2s) -> EM"]
        else:
            return
        name = random.choice(options)
        _run_blink_by_name(name, delay)
        _schedule_blink_after_talking()

    def _get_mic_threshold():
        raw = mic_threshold_var.get().strip()
        try:
            val = float(raw)
        except ValueError:
            messagebox.showerror("Invalid Threshold", "Enter a numeric trigger threshold.")
            return None
        if val <= 0:
            messagebox.showerror(
                "Invalid Threshold", "Trigger threshold must be > 0."
            )
            return None
        return val

    def _get_mic_release_ms():
        raw = mic_release_var.get().strip()
        try:
            val = int(float(raw))
        except ValueError:
            messagebox.showerror(
                "Invalid Release", "Enter a numeric release time in milliseconds."
            )
            return None
        if val < 0:
            messagebox.showerror(
                "Invalid Release", "Release time must be 0 or greater."
            )
            return None
        return val

    def _mic_level(indata):
        if np is not None:
            return float(np.sqrt(np.mean(indata ** 2)))
        total = 0.0
        count = 0
        for sample in indata.flatten():
            total += float(sample) * float(sample)
            count += 1
        return (total / count) ** 0.5 if count else 0.0

    def _mic_callback(indata, frames, time_info, status):
        window_ref["mic_level"] = _mic_level(indata)

    def _mic_poll():
        threshold = _get_mic_threshold()
        if threshold is None:
            window_ref["mic_poll_after_id"] = root.after(100, _mic_poll)
            return
        release_ms = _get_mic_release_ms()
        if release_ms is None:
            window_ref["mic_poll_after_id"] = root.after(100, _mic_poll)
            return
        window_ref["mic_threshold"] = threshold
        level = window_ref["mic_level"] * 100.0
        threshold = window_ref["mic_threshold"]
        if window_ref["happy_active"]:
            mic_status_var.set(f"Mic: {level:.3f} {'>=' if level >= threshold else '<'} {threshold:.3f}")
            window_ref["mic_poll_after_id"] = root.after(100, _mic_poll)
            return
        if window_ref["sad_active"]:
            mic_status_var.set(f"Mic: {level:.3f} {'>=' if level >= threshold else '<'} {threshold:.3f}")
            window_ref["mic_poll_after_id"] = root.after(100, _mic_poll)
            return
        if level >= threshold:
            mic_status_var.set(f"Mic: {level:.3f} >= {threshold:.3f}")
            window_ref["mic_below_since"] = None
            if not window_ref["mic_talking_active"]:
                window_ref["mic_talking_active"] = True
                _start_talking_delay_updates()
                if not talking_var.get():
                    talking_var.set(True)
                if window_ref["img_window"] is None or not window_ref["img_window"].winfo_exists():
                    open_image_window()
                else:
                    _start_talking()
        else:
            mic_status_var.set(f"Mic: {level:.3f} < {threshold:.3f}")
            if window_ref["mic_talking_active"]:
                if window_ref["mic_below_since"] is None:
                    window_ref["mic_below_since"] = time.monotonic()
                else:
                    if time.monotonic() - window_ref["mic_below_since"] >= (
                        release_ms / 1000.0
                    ):
                        window_ref["mic_talking_active"] = False
                        window_ref["mic_below_since"] = None
                        if talking_var.get():
                            talking_var.set(False)
                        _cancel_talking()
                        _cancel_talking_delay_update()
                        _start_animation()
                        _schedule_blink_after_talking()
        window_ref["mic_poll_after_id"] = root.after(100, _mic_poll)

    def _start_mic_stream(device_index):
        if not MIC_AVAILABLE:
            messagebox.showerror(
                "Microphone Error",
                "sounddevice/numpy not available. Install them to use mic input.",
            )
            return
        _cancel_mic()
        try:
            stream = sd.InputStream(
                device=device_index, channels=1, callback=_mic_callback
            )
            stream.start()
            window_ref["mic_stream"] = stream
            window_ref["mic_poll_after_id"] = root.after(100, _mic_poll)
        except Exception as exc:
            messagebox.showerror("Microphone Error", str(exc))

    def _on_mic_select(name):
        if not name:
            return
        device_index = mic_device_map.get(name)
        if device_index is None:
            return
        _start_mic_stream(device_index)

    def _get_talking_delay_ms():
        raw = talking_delay_var.get().strip()
        try:
            delay = int(float(raw))
        except ValueError:
            messagebox.showerror(
                "Invalid Talking Delay", "Enter a numeric talking delay in milliseconds."
            )
            return None
        if delay < 1:
            messagebox.showerror(
                "Invalid Talking Delay", "Talking delay must be at least 1 ms."
            )
            return None
        return delay

    def _get_talking_delay_range_ms():
        try:
            min_ms = int(float(talking_min_delay_var.get().strip()))
            max_ms = int(float(talking_max_delay_var.get().strip()))
        except ValueError:
            messagebox.showerror(
                "Invalid Talking Range", "Enter numeric min/max talking delay (ms)."
            )
            return None
        if min_ms < 1 or max_ms < 1 or max_ms < min_ms:
            messagebox.showerror(
                "Invalid Talking Range", "Min/Max must be >= 1 and Max >= Min."
            )
            return None
        return min_ms, max_ms

    def _get_update_randomizer_range_ms():
        try:
            min_s = float(update_rand_min_var.get().strip())
            max_s = float(update_rand_max_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "Invalid Randomizer Range",
                "Enter numeric min/max update randomizer seconds.",
            )
            return None
        if min_s < 0 or max_s < 0 or max_s < min_s:
            messagebox.showerror(
                "Invalid Randomizer Range", "Min/Max must be >= 0 and Max >= Min."
            )
            return None
        return int(min_s * 1000), int(max_s * 1000)

    def _apply_random_talking_delay():
        rng = _get_talking_delay_range_ms()
        if rng is None:
            return False
        min_ms, max_ms = rng
        talking_delay_var.set(str(random.randint(min_ms, max_ms)))
        return True

    def _talking_delay_update_tick():
        window_ref["talking_delay_update_id"] = None
        if not talking_var.get() and not window_ref["mic_talking_active"]:
            return
        if not _apply_random_talking_delay():
            return
        rng = _get_update_randomizer_range_ms()
        if rng is None:
            return
        min_ms, max_ms = rng
        delay_ms = random.randint(min_ms, max_ms)
        window_ref["talking_delay_update_id"] = root.after(
            delay_ms, _talking_delay_update_tick
        )

    def _start_talking_delay_updates():
        _cancel_talking_delay_update()
        if not talking_var.get() and not window_ref["mic_talking_active"]:
            return
        if not _apply_random_talking_delay():
            return
        rng = _get_update_randomizer_range_ms()
        if rng is None:
            return
        min_ms, max_ms = rng
        delay_ms = random.randint(min_ms, max_ms)
        window_ref["talking_delay_update_id"] = root.after(
            delay_ms, _talking_delay_update_tick
        )

    def _talking_step():
        if (
            not talking_var.get()
            or window_ref["img_window"] is None
            or not window_ref["img_window"].winfo_exists()
        ):
            _cancel_talking()
            return
        if window_ref["happy_active"]:
            _cancel_talking()
            return
        if window_ref["sad_active"]:
            _cancel_talking()
            return

        if window_ref["talking_show_initial"]:
            path = _build_talking_path(window_ref["talking_initial_mouth_open"])
            ok = _set_image_by_path(path)
            if not ok:
                _cancel_talking()
                return
            window_ref["talking_show_initial"] = False
        else:
            rand_base = random.choice(["HU_", "HD_"])
            path = _build_talking_path(True, base_override=rand_base)
            if not _set_image_by_path(path):
                _cancel_talking()
                return
            window_ref["talking_show_initial"] = True

        delay = _get_talking_delay_ms()
        if delay is None:
            _cancel_talking()
            return
        window_ref["talking_after_id"] = root.after(delay, _talking_step)

    def _start_talking():
        _cancel_animation()
        _cancel_talking()
        if window_ref["img_label"] is None:
            return
        if window_ref["happy_active"]:
            return
        if window_ref["sad_active"]:
            return
        _start_talking_delay_updates()
        window_ref["talking_base"] = random.choice(["HU_", "HD_"])
        window_ref["talking_initial_mouth_open"] = mouth_var.get()
        window_ref["talking_show_initial"] = True
        if not _set_image_by_path(_build_talking_path(window_ref["talking_initial_mouth_open"])):
            return
        delay = _get_talking_delay_ms()
        if delay is None:
            return
        window_ref["talking_after_id"] = root.after(delay, _talking_step)

    def _on_talking_toggle():
        if talking_var.get():
            _start_talking_delay_updates()
            _start_talking()
            return
        _cancel_talking()
        _cancel_talking_delay_update()
        _start_animation()
        _schedule_blink_after_talking()

    def _start_happy_animation():
        if window_ref["img_window"] is None or not window_ref["img_window"].winfo_exists():
            window_ref["happy_active"] = True
            open_image_window()
            return
        _cancel_animation()
        _cancel_blink()
        _cancel_blink_hold()
        _cancel_talking()
        _cancel_blink_after_talking()
        _cancel_talking_delay_update()
        _cancel_sad()
        window_ref["happy_active"] = True

        base_paths = [
            os.path.join(os.path.dirname(__file__), "HU_Happy.png"),
            os.path.join(os.path.dirname(__file__), "HD_Happy.png"),
        ]
        overlay_paths = [
            os.path.join(os.path.dirname(__file__), "Heart_1.png"),
            os.path.join(os.path.dirname(__file__), "Heart_2.png"),
        ]

        missing = [p for p in base_paths + overlay_paths if not os.path.exists(p)]
        if missing:
            messagebox.showerror("Missing File", "Image not found:\n" + "\n".join(missing))
            window_ref["happy_active"] = False
            return

        window_ref["happy_base_images"] = [_load_png_image(p) for p in base_paths]
        window_ref["happy_overlay_images"] = [_load_png_image(p) for p in overlay_paths]
        window_ref["happy_base_index"] = 0
        window_ref["happy_overlay_index"] = 0

        def tick():
            if not window_ref["happy_active"]:
                return
            base_path = base_paths[window_ref["happy_base_index"]]
            overlay_path = overlay_paths[window_ref["happy_overlay_index"]]
            composed = _composite_png_images(base_path, overlay_path)
            if composed is not None:
                window_ref["img_label"].configure(image=composed)
                if window_ref["overlay_label"] is not None:
                    window_ref["overlay_label"].configure(image="")
                window_ref["img_objs"] = [composed]
            else:
                base_img = window_ref["happy_base_images"][window_ref["happy_base_index"]]
                overlay_img = window_ref["happy_overlay_images"][window_ref["happy_overlay_index"]]
                window_ref["img_label"].configure(image=base_img)
                if window_ref["overlay_label"] is not None:
                    window_ref["overlay_label"].configure(image=overlay_img)
                    window_ref["overlay_label"].lift()
                window_ref["img_objs"] = [base_img, overlay_img]
            window_ref["happy_base_index"] = 1 - window_ref["happy_base_index"]
            window_ref["happy_overlay_index"] = 1 - window_ref["happy_overlay_index"]
            delay = _get_delay_ms()
            if delay is None:
                return
            window_ref["happy_after_id"] = root.after(delay, tick)

        tick()

    def _start_sad_animation():
        if window_ref["img_window"] is None or not window_ref["img_window"].winfo_exists():
            window_ref["sad_active"] = True
            open_image_window()
            return
        _cancel_animation()
        _cancel_blink()
        _cancel_blink_hold()
        _cancel_talking()
        _cancel_blink_after_talking()
        _cancel_talking_delay_update()
        _cancel_happy()
        window_ref["sad_active"] = True

        base_paths = [
            os.path.join(os.path.dirname(__file__), "HU_Sad.png"),
            os.path.join(os.path.dirname(__file__), "HD_Sad.png"),
        ]
        overlay_paths = [
            os.path.join(os.path.dirname(__file__), "Broken_1.png"),
            os.path.join(os.path.dirname(__file__), "Broken_2.png"),
        ]

        missing = [p for p in base_paths + overlay_paths if not os.path.exists(p)]
        if missing:
            messagebox.showerror("Missing File", "Image not found:\n" + "\n".join(missing))
            window_ref["sad_active"] = False
            return

        window_ref["sad_base_images"] = [_load_png_image(p) for p in base_paths]
        window_ref["sad_overlay_images"] = [_load_png_image(p) for p in overlay_paths]
        window_ref["sad_base_index"] = 0
        window_ref["sad_overlay_index"] = 0

        def tick():
            if not window_ref["sad_active"]:
                return
            base_path = base_paths[window_ref["sad_base_index"]]
            overlay_path = overlay_paths[window_ref["sad_overlay_index"]]
            composed = _composite_png_images(base_path, overlay_path)
            if composed is not None:
                window_ref["img_label"].configure(image=composed)
                if window_ref["overlay_label"] is not None:
                    window_ref["overlay_label"].configure(image="")
                window_ref["img_objs"] = [composed]
            else:
                base_img = window_ref["sad_base_images"][window_ref["sad_base_index"]]
                overlay_img = window_ref["sad_overlay_images"][window_ref["sad_overlay_index"]]
                window_ref["img_label"].configure(image=base_img)
                if window_ref["overlay_label"] is not None:
                    window_ref["overlay_label"].configure(image=overlay_img)
                    window_ref["overlay_label"].lift()
                window_ref["img_objs"] = [base_img, overlay_img]
            window_ref["sad_base_index"] = 1 - window_ref["sad_base_index"]
            window_ref["sad_overlay_index"] = 1 - window_ref["sad_overlay_index"]
            delay = _get_delay_ms()
            if delay is None:
                return
            window_ref["sad_after_id"] = root.after(delay, tick)

        tick()

    def _stop_emotion_animation():
        _cancel_happy()
        _cancel_sad()
        if window_ref["overlay_label"] is not None:
            window_ref["overlay_label"].configure(image="")
        if window_ref["img_window"] is None or not window_ref["img_window"].winfo_exists():
            return
        if talking_var.get():
            _start_talking()
        else:
            _start_animation()

    def on_close_main():
        try:
            _cancel_animation()
            _cancel_blink()
            _cancel_blink_hold()
            _cancel_talking()
            _cancel_blink_after_talking()
            _cancel_talking_delay_update()
            _cancel_happy()
            _cancel_sad()
            _cancel_mic()
            if window_ref["img_window"] is not None and window_ref["img_window"].winfo_exists():
                window_ref["img_window"].destroy()
        finally:
            root.quit()
            root.destroy()
            sys.exit(0)

    start_btn = tk.Button(root, text="Start", width=20, command=open_image_window)
    start_btn.pack(padx=20, pady=10)

    def _set_controls_state(enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in (
            eyes_rb_open,
            eyes_rb_med,
            eyes_rb_closed,
            mouth_cb,
            blink_menu,
            blink_play_btn,
        ):
            widget.configure(state=state)

    def _on_debug_toggle():
        if debug_var.get():
            _set_controls_state(True)
            _update_blink_menu()
            return
        _cancel_blink()
        _cancel_blink_hold()
        mouth_var.set(False)
        eyes_var.set("EO_")
        _update_blink_menu()
        _set_controls_state(False)

    delay_row = tk.Frame(root)
    delay_row.pack(padx=20, pady=5)
    tk.Label(delay_row, text="Delay (ms):").pack(side=tk.LEFT)
    delay_entry = tk.Entry(delay_row, textvariable=delay_var, width=10)
    delay_entry.pack(side=tk.LEFT, padx=6)

    talking_row = tk.Frame(root)
    talking_row.pack(padx=20, pady=5)
    talking_cb = tk.Checkbutton(
        talking_row, text="Talking", variable=talking_var, command=_on_talking_toggle
    )
    talking_cb.pack(side=tk.LEFT)
    tk.Label(talking_row, text="Talking Delay (ms):").pack(side=tk.LEFT, padx=6)
    talking_delay_entry = tk.Entry(
        talking_row, textvariable=talking_delay_var, width=10
    )
    talking_delay_entry.pack(side=tk.LEFT)

    happy_row = tk.Frame(root)
    happy_row.pack(padx=20, pady=5)
    happy_btn = tk.Button(happy_row, text="Happy", width=10, command=_start_happy_animation)
    happy_btn.pack(side=tk.LEFT, padx=6)
    stop_happy_btn = tk.Button(
        happy_row, text="Stop", width=10, command=_stop_emotion_animation
    )
    stop_happy_btn.pack(side=tk.LEFT)

    sad_row = tk.Frame(root)
    sad_row.pack(padx=20, pady=5)
    sad_btn = tk.Button(sad_row, text="Sad", width=10, command=_start_sad_animation)
    sad_btn.pack(side=tk.LEFT, padx=6)

    talking_range_row = tk.Frame(root)
    talking_range_row.pack(padx=20, pady=5)
    tk.Label(talking_range_row, text="Talking Min (ms):").pack(side=tk.LEFT)
    talking_min_entry = tk.Entry(
        talking_range_row, textvariable=talking_min_delay_var, width=8
    )
    talking_min_entry.pack(side=tk.LEFT, padx=6)
    tk.Label(talking_range_row, text="Talking Max (ms):").pack(side=tk.LEFT, padx=6)
    talking_max_entry = tk.Entry(
        talking_range_row, textvariable=talking_max_delay_var, width=8
    )
    talking_max_entry.pack(side=tk.LEFT)

    update_rand_row = tk.Frame(root)
    update_rand_row.pack(padx=20, pady=5)
    tk.Label(update_rand_row, text="Update Randomizer Min (s):").pack(side=tk.LEFT)
    update_rand_min_entry = tk.Entry(
        update_rand_row, textvariable=update_rand_min_var, width=6
    )
    update_rand_min_entry.pack(side=tk.LEFT, padx=6)
    tk.Label(update_rand_row, text="Update Randomizer Max (s):").pack(
        side=tk.LEFT, padx=6
    )
    update_rand_max_entry = tk.Entry(
        update_rand_row, textvariable=update_rand_max_var, width=6
    )
    update_rand_max_entry.pack(side=tk.LEFT)

    blink_after_row = tk.Frame(root)
    blink_after_row.pack(padx=20, pady=5)
    blink_after_cb = tk.Checkbutton(
        blink_after_row,
        text="Blinking After Talking",
        variable=blink_after_talking_var,
        command=_schedule_blink_after_talking,
    )
    blink_after_cb.pack(side=tk.LEFT)
    tk.Label(blink_after_row, text="Min (s):").pack(side=tk.LEFT, padx=6)
    blink_after_min_entry = tk.Entry(
        blink_after_row, textvariable=blink_after_min_var, width=6
    )
    blink_after_min_entry.pack(side=tk.LEFT)
    tk.Label(blink_after_row, text="Max (s):").pack(side=tk.LEFT, padx=6)
    blink_after_max_entry = tk.Entry(
        blink_after_row, textvariable=blink_after_max_var, width=6
    )
    blink_after_max_entry.pack(side=tk.LEFT)

    mic_device_map = {}
    mic_row = tk.Frame(root)
    mic_row.pack(padx=20, pady=5)
    tk.Label(mic_row, text="Mic Input:").pack(side=tk.LEFT)
    mic_menu = tk.OptionMenu(mic_row, mic_var, "")
    mic_menu.configure(width=28)
    mic_menu.pack(side=tk.LEFT, padx=6)
    tk.Label(mic_row, text="Trigger Threshold:").pack(side=tk.LEFT, padx=6)
    mic_threshold_entry = tk.Entry(mic_row, textvariable=mic_threshold_var, width=8)
    mic_threshold_entry.pack(side=tk.LEFT)
    tk.Label(mic_row, text="Release (ms):").pack(side=tk.LEFT, padx=6)
    mic_release_entry = tk.Entry(mic_row, textvariable=mic_release_var, width=8)
    mic_release_entry.pack(side=tk.LEFT)
    mic_status_lbl = tk.Label(mic_row, textvariable=mic_status_var, width=24, anchor="w")
    mic_status_lbl.pack(side=tk.LEFT, padx=6)

    debug_row = tk.Frame(root)
    debug_row.pack(padx=20, pady=5)
    debug_cb = tk.Checkbutton(
        debug_row, text="DEBUG", variable=debug_var, command=_on_debug_toggle
    )
    debug_cb.pack(side=tk.LEFT)

    eyes_row = tk.Frame(root)
    eyes_row.pack(padx=20, pady=5)
    tk.Label(eyes_row, text="Eyes:").pack(side=tk.LEFT)
    eyes_rb_open = tk.Radiobutton(
        eyes_row, text="Eyes Open", variable=eyes_var, value="EO_"
    )
    eyes_rb_open.pack(side=tk.LEFT, padx=6)
    eyes_rb_med = tk.Radiobutton(
        eyes_row, text="Eyes Medium", variable=eyes_var, value="EM_"
    )
    eyes_rb_med.pack(side=tk.LEFT, padx=6)
    eyes_rb_closed = tk.Radiobutton(
        eyes_row, text="Eyes Closed", variable=eyes_var, value="EC_"
    )
    eyes_rb_closed.pack(side=tk.LEFT, padx=6)

    mouth_row = tk.Frame(root)
    mouth_row.pack(padx=20, pady=5)
    mouth_cb = tk.Checkbutton(mouth_row, text="Mouth Open", variable=mouth_var)
    mouth_cb.pack(side=tk.LEFT)

    blink_row = tk.Frame(root)
    blink_row.pack(padx=20, pady=5)
    tk.Label(blink_row, text="Blink:").pack(side=tk.LEFT)
    blink_menu = tk.OptionMenu(blink_row, blink_var, "")
    blink_menu.configure(width=26)
    blink_menu.pack(side=tk.LEFT, padx=6)
    blink_play_btn = tk.Button(blink_row, text="Play", width=10, command=_play_blink)
    blink_play_btn.pack(side=tk.LEFT)

    eyes_var.trace_add("write", lambda *_: _update_blink_menu())

    _set_controls_state(False)

    update_btn = tk.Button(root, text="Update", width=20, command=update_animation)
    update_btn.pack(padx=20, pady=10)

    if MIC_AVAILABLE:
        try:
            devices = sd.query_devices()
            options = []
            for i, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    label = f"{i}: {d.get('name')}"
                    mic_device_map[label] = i
                    options.append(label)
            menu = mic_menu["menu"]
            menu.delete(0, "end")
            for opt in options:
                menu.add_command(
                    label=opt,
                    command=lambda v=opt: (mic_var.set(v), _on_mic_select(v)),
                )
            if options:
                mic_var.set(options[0])
                _on_mic_select(options[0])
        except Exception as exc:
            messagebox.showerror("Microphone Error", str(exc))
    else:
        mic_menu.configure(state=tk.DISABLED)
        mic_threshold_entry.configure(state=tk.DISABLED)
        mic_release_entry.configure(state=tk.DISABLED)
        mic_status_var.set("Mic: unavailable")

    root.protocol("WM_DELETE_WINDOW", on_close_main)
    root.mainloop()


if __name__ == "__main__":
    main()
