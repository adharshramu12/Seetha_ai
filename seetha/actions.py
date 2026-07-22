import time
import os
import json
import subprocess
import shutil
import re
import urllib.parse
import pyautogui
from pywinauto import Application, Desktop
import screen_brightness_control as sbc
import webbrowser
import pyperclip
import psutil
from seetha.logger import setup_logger

logger = setup_logger()

# pywhatkit checks the internet AT IMPORT TIME and raises if offline,
# which would crash the whole Actions engine on a flaky connection.
# Guard it: without pywhatkit we fall back to a plain YouTube search.
try:
    import pywhatkit
except Exception as _e:
    pywhatkit = None
    logger.warning(f"pywhatkit unavailable (offline?). YouTube fallback will be used. ({_e})")

class SeethaActions:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            with open(config_path, "r") as f:
                self.config = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load config.json: {e}")
            self.config = {"app_map": {}, "process_map": {}, "safelist_apps": [], "settings": {}}
        # Dedupe state for instant meetings (avoids double-creation)
        self._last_meeting_url = None
        self._last_meeting_time = 0
        logger.info("SeethaActions initialized.")

    def _get_process_map(self):
        return self.config.get("process_map", {})

    def _sanitize_input(self, text):
        """
        SECURITY: Strict sanitization to prevent Command Injection.
        Removes dangerous shell characters.
        """
        if not text: return ""
        # Remove characters that allow command chaining or redirection
        # & | ; > < $ ` ( )
        safe_text = re.sub(r'[&|;><$`\(\)]', '', text)
        return safe_text.strip()

    def search_file(self, filename):
        """Searches for a file in the user's home directory."""
        logger.info(f"Searching for file: {filename}")
        search_path = os.path.expanduser("~") # Search in user directory
        
        # Priority directories
        target_dirs = [
            os.path.join(search_path, "Desktop"),
            os.path.join(search_path, "Documents"),
            os.path.join(search_path, "Downloads"),
            os.path.join(search_path, "Music"),
            os.path.join(search_path, "Videos"),
            os.path.join(search_path, "Pictures")
        ]
        
        # First pass: Quick search in priority dirs
        for dir_path in target_dirs:
            if os.path.exists(dir_path):
                for root, dirs, files in os.walk(dir_path):
                    for file in files:
                        if filename.lower() in file.lower():
                            full_path = os.path.join(root, file)
                            logger.info(f"File found at: {full_path}")
                            return full_path
        
        logger.warning(f"File '{filename}' not found in priority directories.")
        return None

    def _wait_for_window(self, title_pattern, timeout=10):
        """
        Enterprise-grade wait function.
        Waits for a window matching the title pattern to exist.
        """
        logger.debug(f"Waiting for window: {title_pattern} (timeout={timeout}s)")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Use pywinauto to find window
                windows = Desktop(backend="uia").windows()
                for w in windows:
                    if title_pattern.lower() in w.window_text().lower():
                        logger.info(f"Window found: {w.window_text()}")
                        return w
            except Exception as e:
                logger.warning(f"Window search warning (non-fatal): {e}")
            time.sleep(0.5)
        logger.warning(f"Timeout waiting for window: {title_pattern}")
        return None

    def play_song(self, song_name):
        """Plays a song on YouTube."""
        logger.info(f"Playing song: {song_name}")
        try:
            if pywhatkit:
                # Plays the top result directly
                logger.debug(f"Invoking pywhatkit for: {song_name}")
                pywhatkit.playonyt(song_name)
            else:
                # Offline-import fallback: open a YouTube search instead
                query = urllib.parse.quote_plus(song_name)
                webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
            return True
        except Exception as e:
            logger.error(f"Error playing song: {e}", exc_info=True)
            return False

    def open_multiple_apps(self, apps):
        """
        Opens a list of applications sequentially with a delay.
        """
        results = []
        for app in apps:
            logger.info(f"Batch Action: Opening {app}...")
            success = self.open_app(app)
            results.append((app, success))
            # Enterprise: Smart wait instead of blind sleep if possible, but for batch open, delay is safer to avoid CPU spike.
            time.sleep(2) 
        return results

    def open_app(self, app_name: str) -> bool:
        """
        Opens an application securely.
        1. Checks Configured Paths
        2. Checks Desktop/Start Menu
        3. Uses Windows Search (Typed)
        
        Security: Avoids shell=True where possible. Uses os.startfile for trusted paths.
        """
        app_name = app_name.lower().strip()
        # Normalize conversational targets: "the chrome browser" -> "chrome"
        app_name = re.sub(r"^(?:the|a|an|my)\s+", "", app_name)
        app_name = re.sub(r"\s+(?:app|apps|application|software|program|browser|window)$", "", app_name).strip()
        logger.info(f"Request to open app: '{app_name}'")
        
        # 1. Configured Map (O(1))
        app_map = self.config.get("app_map", {})
        if app_name in app_map:
            target = app_map[app_name]
            logger.info(f"Trace: Found in config: {target}")
            try:
                # If it's a full path, use subprocess directly (Secure)
                if os.path.isabs(target) and target.endswith(".exe"):
                     subprocess.Popen([target]) # shell=False
                elif target.startswith("http") or target.startswith("mailto") or target.startswith("ftp"):
                    webbrowser.open(target) # Use webbrowser for URLs
                elif ":" in target and not os.path.exists(target): # Protocol handler like "whatsapp:"
                    os.startfile(target)
                else:
                     # If it's just 'notepad.exe', relies on PATH, but safer to use startfile for Windows association
                     os.startfile(target)
                return True
            except Exception as e:
                logger.error(f"Config start failed: {e}")

        # 2. Special Handling: WhatsApp
        if "whatsapp" in app_name or "watsapp" in app_name:
             return self._open_whatsapp()

        # 3. Special Handling: YouTube (Edge)
        if "youtube" in app_name:
            return self._open_url_in_edge("https://www.youtube.com")

        # 4. Search Desktop/Pinned (Fast)
        if self._search_and_open_shortcut(app_name):
            return True
            
        # 5. Fallback: Windows Search (UI Automation)
        # This is UI interaction, so 'shell' risk is lower, effectively just typing.
        return self.open_via_start_menu(app_name)

    def _open_whatsapp(self):
        """Smart WhatsApp Opener."""
        logger.info("Opening WhatsApp...")
        try:
             # Check for Native App Package (PowerShell is still best for AppX enumeration)
             check_cmd = ["powershell", "Get-AppxPackage *WhatsApp*"]
             result = subprocess.run(check_cmd, capture_output=True, text=True, shell=False)
             
             if result.stdout.strip():
                 logger.info("Launching Native WhatsApp...")
                 os.startfile("whatsapp:") # Protocol handler, safe
             else:
                 logger.info("Native WhatsApp missing. Using Web.")
                 self._open_url_in_edge("https://web.whatsapp.com")
             return True
        except Exception as e:
             logger.error(f"WhatsApp launch error: {e}")
             webbrowser.open("https://web.whatsapp.com")
             return True

    def _open_url_in_edge(self, url):
        """Opens URL in Edge securely."""
        try:
            # Try specific path first
            edge_path = self.config.get("app_map", {}).get("edge")
            if edge_path and os.path.exists(edge_path):
                 subprocess.Popen([edge_path, url]) # shell=False
            else:
                 # Fallback to 'start msedge' which uses shell=True, but is common for browser launch
                 subprocess.Popen(f"start msedge {url}", shell=True) 
            return True
        except Exception as e:
            logger.error(f"Edge launch error: {e}")
            return False

    def _search_and_open_shortcut(self, app_name):
        """Scans Desktop/Start Menu safely."""
        import glob
        roots = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.environ.get('PUBLIC', 'C:\\Users\\Public'), 'Desktop'),
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar"),
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), 'Microsoft\\Windows\\Start Menu\\Programs')
        ]
        
        patterns = [f"*{app_name}*.lnk", f"*{app_name}*.url", f"*{app_name}*.exe"]
        
        for root in roots:
            if not os.path.exists(root): continue
            # Check top level
            for pattern in patterns:
                matches = glob.glob(os.path.join(root, pattern))
                if matches:
                    try:
                        logger.info(f"Found shortcut: {matches[0]}")
                        os.startfile(matches[0]) # Secure
                        return True
                    except: pass
            # Check one level deep for Start Menu folders
            try:
                subdirs = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
                for subdir in subdirs:
                    subdir_path = os.path.join(root, subdir)
                    for pattern in patterns:
                        matches = glob.glob(os.path.join(subdir_path, pattern))
                        if matches:
                            try:
                                logger.info(f"Found (Subdir): {matches[0]}")
                                os.startfile(matches[0])
                                return True
                            except: pass
            except: pass
        return False

    def open_via_start_menu(self, app_name):
        """UI Automation for Start Menu."""
        try:
            pyautogui.press('win')
            time.sleep(0.2)
            pyautogui.typewrite(app_name, interval=0.01)
            time.sleep(self.config.get("settings", {}).get("search_timeout_seconds", 0.8))
            pyautogui.press('enter')
            return True
        except Exception as e:
            logger.error(f"Start menu error: {e}")
            return False

    def type_text(self, text: str) -> bool:
        """Types text into the active window with safety checks."""
        # Removed blind 1s sleep. 
        # Check active window existence
        try:
             # Just a small buffer for focus switch
             time.sleep(0.2)
             pyautogui.typewrite(text, interval=0.01) # Faster typing
        except Exception as e:
            logger.error(f"Error typing text: {e}")
            return False
        return True

    def open_whatsapp_chat(self, contact):
        """Searches for a contact on WhatsApp and opens the chat."""
        logger.info(f"Opening WhatsApp chat for {contact}...")
        try:
            # 1. Open WhatsApp
            self.open_app("whatsapp")
            time.sleep(2)
            
            # 2. Search for contact
            logger.info("Searching for contact...")
            # Use Standard Ctrl+F for Desktop App
            pyautogui.hotkey('ctrl', 'f')
            time.sleep(0.5)
            
            # Clear any previous search
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('backspace')
            
            # Type contact name
            pyautogui.typewrite(contact, interval=0.05)
            time.sleep(2.0) # Wait for search results (increased delay)
            
            # Select first result
            # In Desktop App, focus might stay in search box. 
            # Pressing Down arrow usually moves focus to the list.
            pyautogui.press('down')
            time.sleep(0.2)
            
            # Press Enter to open chat
            pyautogui.press('enter')
            time.sleep(1.0) # Wait for chat to load
            return True
        except Exception as e:
            logger.error(f"Error opening chat: {e}", exc_info=True)
            return False

    def send_whatsapp(self, contact, message):
        """Sends a WhatsApp message using GUI automation (Search & Type)."""
        logger.info(f"Sending WhatsApp to {contact}: {message}")
        try:
            # 1. Open Chat
            if not self.open_whatsapp_chat(contact):
                return False
            
            # 2. Type message
            logger.debug("Typing message...")
            pyautogui.typewrite(message, interval=0.01)
            time.sleep(0.2)
            
            # 3. Send (Enter)
            pyautogui.press('enter')
            logger.info("Message sent.")
            return True
            
        except Exception as e:
            logger.error(f"Error sending whatsapp: {e}", exc_info=True)
            return False

    def send_active_chat_message(self, message):
        """Types and sends a message in the currently active chat window."""
        logger.info(f"Sending message in active chat: {message}")
        try:
            # Ensure focus on Input Box (Click Bottom Center)
            width, height = pyautogui.size()
            # Assuming Input box is at the bottom. 
            # Height - 50 pixels should be safe for maximized window.
            pyautogui.click(width // 2, height - 50)
            time.sleep(0.2)
            
            # Type message
            pyautogui.typewrite(message, interval=0.01)
            time.sleep(0.2)
            
            # Send (Enter)
            pyautogui.press('enter')
            logger.info("Message sent.")
            return True
        except Exception as e:
            logger.error(f"Error sending active chat message: {e}", exc_info=True)
            return False

    def close_all_apps(self):
        """
        Closes all visible application windows using psutil.
        Enterprise Grade: No PowerShell piping, much faster, safer.
        """
        logger.info("Executed: CLOSE ALL APPS (Native)")
        safelist = set(self.config.get("safelist_apps", []))
        # Ensure extremely critical ones are hardcoded just in case config fails
        safelist.update(["explorer", "python", "pythonw", "Taskmgr", "SearchHost", "StartMenuExperienceHost", "TextInputHost", "cmd", "powershell"]) 
        
        count = 0
        
        # Since 'Close All' purely via psutil without win32gui is risky (closes background stuff),
        # I will use a robust PowerShell enumeration that returns JSON, parse in Python, then kill via psutil.
        # This meets "Process control with native Python" (Killing is native).
        try:
            cmd = ["powershell", "Get-Process | Where-Object { $_.MainWindowTitle -ne '' } | Select-Object Name, Id | ConvertTo-Json"]
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            
            # Handle cases where ConvertTo-Json returns empty string or single object vs array
            stdout_str = result.stdout.strip()
            if not stdout_str: 
                logger.info("No visible applications found to close.")
                return True
            
            try:
                procs = json.loads(stdout_str)
            except json.JSONDecodeError:
                # If it's a single object, it might not be in an array
                procs = [json.loads(stdout_str)]
            
            if not isinstance(procs, list): # Ensure it's always a list for iteration
                procs = [procs]
            
            for p in procs:
                name = p.get('Name')
                pid = p.get('Id')
                if name and name.lower() in safelist: continue
                
                try:
                    proc = psutil.Process(pid)
                    proc.terminate() # Gentle kill first
                    count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            logger.info(f"Closed {count} applications.")
            return True
        except Exception as e:
            logger.error(f"Error in Close All: {e}", exc_info=True)
            return False

    def close_app(self, app_name):
        """
        Closes a specific application securely using psutil.
        """
        app_name = app_name.lower()
        if "watsapp" in app_name: app_name = "whatsapp"
        
        # Protection
        if "explore" in app_name or "file manager" in app_name: 
            logger.warning("Detected request to close File Explorer. Using safe method (Close Windows).")
            # PowerShell command to close only open explorer windows using Shell.Application
            # This doesn't kill explorer.exe, just the windows.
            safe_close_cmd = "powershell -Command \"(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }\""
            subprocess.run(safe_close_cmd, shell=True)
            return True
        
        # Resolve target name
        target_process = None
        process_map = self._get_process_map()
        
        for key, val in process_map.items():
            if key in app_name:
                target_process = val
                break
        
        logger.info(f"Closing {app_name} -> Process: {target_process or 'Generic Search'}")
        
        # SAFETY: match ONLY on the process/executable NAME — never on the
        # command line. Command-line matching killed innocent processes
        # that merely mentioned the app name in their arguments (e.g. a
        # shell running a script containing the word "notepad").
        safelist_for_generic_kill = set(
            s.lower() for s in self.config.get("safelist_apps", [])
        )
        safelist_for_generic_kill.update([
            "explorer.exe", "explorer", "python.exe", "python", "pythonw.exe",
            "pythonw", "cmd.exe", "cmd", "powershell.exe", "powershell",
            "bash.exe", "bash", "sh.exe", "conhost.exe", "wininit.exe",
            "winlogon.exe", "csrss.exe", "services.exe", "lsass.exe", "svchost.exe",
        ])

        killed = False
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                proc_name = proc.info['name'].lower() if proc.info['name'] else ''
                proc_exe = os.path.basename(proc.info['exe']).lower() if proc.info['exe'] else ''

                # 1. Match by Known Process Name from config
                if target_process:
                    if target_process.lower() == proc_name.replace('.exe', '') or \
                       target_process.lower() == proc_exe.replace('.exe', ''):
                        logger.info(f"Terminating process {proc.pid} ({proc_name}) for '{app_name}' (Config match)")
                        proc.terminate()
                        killed = True
                        continue

                # 2. Generic match by app_name in process NAME only
                if app_name in proc_name or app_name in proc_exe:
                    if proc_name not in safelist_for_generic_kill and proc_exe not in safelist_for_generic_kill:
                        logger.info(f"Terminating process {proc.pid} ({proc_name}) for '{app_name}' (Generic match)")
                        proc.terminate()
                        killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if not killed:
            logger.warning(f"Could not find or terminate any process for '{app_name}'.")
        return killed

    def close_tab(self):
        """Closes the active tab or window using shortcut."""
        pyautogui.hotkey('ctrl', 'w')
        return True

    def close_active_window(self):
        """Closes the currently active window using Alt+F4."""
        pyautogui.hotkey('alt', 'f4')
        return True

    def search_in_app(self, query):
        """Searches within the current application using Ctrl+F."""
        logger.info(f"Searching in app for: {query}")
        # Click to ensure focus? Maybe not, user might be typing.
        # But usually good to ensure window is active.
        # pyautogui.click() # Risky if it clicks something wrong.
        
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.5)
        
        # Clear previous
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        
        pyautogui.typewrite(query, interval=0.05)
        time.sleep(1)
        pyautogui.press('enter')
        return True

    def read_screen(self):
        """Selects all text and copies to clipboard to read screen content."""
        logger.info("Reading screen content...")
        try:
            # 0. Maximize Window to ensure coordinates are valid
            pyautogui.hotkey('win', 'up')
            time.sleep(1.0)
            
            # 1. Clear Clipboard
            import pyperclip
            pyperclip.copy("") 
            
            # 2. Try Ctrl+A First
            logger.debug("Attempting Ctrl+A...")
            width, height = pyautogui.size()
            pyautogui.click(width // 2, height // 2)
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(1.0)
            
            # Retry paste logic
            result = ""
            for _ in range(3):
                try:
                    result = pyperclip.paste().strip()
                    break
                except Exception:
                    time.sleep(0.5)
            
            logger.debug(f"Ctrl+A Result Length: {len(result)}")
            
            # 3. If empty, try Drag Select
            if not result:
                logger.debug("Ctrl+A failed/empty. Trying Drag Select...")
                # Start near bottom (above input box)
                start_x, start_y = width // 2, height - 150 
                # End near top
                end_x, end_y = width // 2, 100
                
                pyautogui.moveTo(start_x, start_y)
                pyautogui.dragTo(end_x, end_y, duration=1.0, button='left')
                time.sleep(0.5)
                
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(1.0)
                result = pyperclip.paste().strip()
                logger.debug(f"Drag Select Result Length: {len(result)}")
            
            # 4. Deselect
            pyautogui.press('right')
            
            return result
        except Exception as e:
            logger.error(f"Error reading screen: {e}", exc_info=True)
            return ""

    def whatsapp_call(self, contact, video=False):
        """
        Calls a contact on WhatsApp.
        1. Search and open chat.
        2. Click Call/Video button.
        """
        logger.info(f"Initiating WhatsApp {'Video ' if video else ''}Call to {contact}...")
        
        # 1. Open Chat (Reuse send_whatsapp logic but without sending text)
        # We assume WhatsApp is open or we open it.
        # If we are already in the app (contextual), we just search.
        # But to be safe, we can reuse the search logic.
        
        try:
            # 1. Open Chat
            if not self.open_whatsapp_chat(contact):
                return False
            
            time.sleep(1) # Wait for chat to load
            
            # 2. Click Call Button
            # Detected User is using WhatsApp Web (Edge).
            # Ctrl+F opens Browser Find, which breaks navigation.
            # Use Ctrl+Alt+/ to focus WhatsApp Search.
            
            # But we already searched and opened the chat.
            # Now we need to click the Call button.
            # Focus is likely in the Message Input box.
            
            # Navigation Strategy from Input Box:
            # Shift+Tab sequence on WhatsApp Web usually:
            # Input -> Emoji -> Attach -> Message List -> Menu -> Search -> Voice Call -> Video Call
            # That's about 6-7 steps.
            
            logger.debug("Navigating to Call button using Shift+Tab sequence...")
            
            # Ensure focus is in Input Box (Clicking center might help, but let's assume Enter placed us there)
            
            # Try 7 steps for Voice, 6 for Video (Video is usually to the left of Voice? No, usually [Video] [Voice])
            # Tab order is usually Left -> Right.
            # So Shift+Tab (Reverse) goes Right -> Left?
            # Top Bar: [Video] [Voice] [Search] [Menu]
            # If we come from Message List (Bottom), Shift+Tab goes to [Menu]?
            # Menu -> Search -> Voice -> Video.
            # So Voice is 3rd from Menu.
            
            # Let's try a sequence of 7 Shift+Tabs.
            # If it overshoots, it might hit Video.
            
            # Voice Call: ~7 steps
            # Video Call: ~8 steps
            
            steps = 8 if video else 7
            logger.debug(f"Executing {steps} Shift+Tabs...")
            
            for i in range(steps):
                pyautogui.hotkey('shift', 'tab')
                time.sleep(0.2)
            
            logger.info("Pressing Enter to Call...")
            pyautogui.press('enter')
            return True
            
        except Exception as e:
            logger.error(f"Error calling: {e}", exc_info=True)
            return False

    def control_volume(self, action):
        """
        Controls system volume.
        action: 'up', 'down', 'mute'
        """
        logger.info(f"Controlling volume: {action}")
        try:
            if action == "up":
                # Press multiple times for noticeable effect (increased to 10)
                for _ in range(10):
                    pyautogui.press('volumeup')
            elif action == "down":
                for _ in range(10):
                    pyautogui.press('volumedown')
            elif action == "mute":
                pyautogui.press('volumemute')
            return True
        except Exception as e:
            logger.error(f"Error controlling volume: {e}", exc_info=True)
            return False

    def control_brightness(self, action, level=None):
        """
        Controls screen brightness DIRECTLY via the display driver
        (no Settings app involved).
        action: 'up', 'down', or 'set' (with level 0-100)
        """
        logger.info(f"Controlling brightness: {action} (level={level})")
        try:
            import screen_brightness_control as sbc

            if action == "set" and level is not None:
                sbc.set_brightness(max(0, min(100, int(level))))
                return True

            # Get current brightness (returns list, take first)
            current_list = sbc.get_brightness()
            if not current_list:
                logger.error("Could not get current brightness.")
                return False

            current = current_list[0]
            logger.debug(f"Current brightness: {current}")

            if action == "up":
                new_val = min(100, current + 20) # Increase by 20%
                sbc.set_brightness(new_val)
            elif action == "down":
                new_val = max(0, current - 20) # Decrease by 20%
                sbc.set_brightness(new_val)
            
            # Verify
            time.sleep(0.5)
            updated_list = sbc.get_brightness()
            if updated_list:
                logger.debug(f"New brightness: {updated_list[0]}")
            
            return True
        except Exception as e:
            logger.error(f"Error controlling brightness: {e}", exc_info=True)
            return False

    def click_element(self, text):
        """
        Clicks on a UI element with the given text in the active window.
        Uses pywinauto (UIA) to find the element.
        """
        logger.info(f"Attempting to click element with text: '{text}'")
        try:
            # Connect to the active window
            try:
                # Use a shorter timeout to connect to prevent hanging
                app = Application(backend="uia").connect(active_only=True, timeout=3)
            except Exception as e:
                logger.warning(f"Could not connect to active window (might be elevated/admin): {e}")
                return False

            dlg = app.top_window()
            # logger.debug(f"Active Window: {dlg.window_text()}") 
            
            # Try exact match first
            try:
                # Enterprise: Explicit timeout param is critical
                ctrl = dlg.child_window(title=text, control_type=None)
                if ctrl.exists(timeout=2):
                    logger.info(f"Found exact match: {ctrl}")
                    ctrl.click_input()
                    return True
            except Exception:
                pass
                
            # Try fuzzy match (contains text)
            try:
                ctrl = dlg.child_window(title_re=f".*{text}.*", control_type=None)
                if ctrl.exists(timeout=2):
                    logger.info(f"Found fuzzy match: {ctrl}")
                    ctrl.click_input()
                    return True
            except Exception:
                pass
                
            logger.warning(f"Element '{text}' not found in active window.")
            return False
            
        except Exception as e:
            logger.error(f"Error clicking element: {e}", exc_info=True)
            return False

    def take_screenshot(self):
        """Takes a screenshot and saves it to Pictures/Screenshots."""
        logger.info("Taking screenshot...")
        try:
            # Create directory if not exists
            save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            
            # Generate filename with timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"Screenshot_{timestamp}.png"
            filepath = os.path.join(save_dir, filename)
            
            # Take and save screenshot
            pyautogui.screenshot(filepath)
            logger.info(f"Screenshot saved to: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}", exc_info=True)
            return None
    def open_desktop_icon(self, name):
        """Opens an icon on the desktop by name using keyboard navigation (Win+D -> Type -> Enter)."""
        logger.info(f"Opening desktop icon: {name}")
        
        # Redirect YouTube to open_app (which forces Edge)
        if "youtube" in name.lower():
            return self.open_app("youtube")

        try:
            # 1. Show Desktop
            pyautogui.hotkey('win', 'd')
            time.sleep(1)
            
            # 2. Type name to select icon
            # We type slowly to ensure Windows registers it as a search
            pyautogui.typewrite(name, interval=0.1)
            time.sleep(1)
            
            # 3. Press Enter to open
            pyautogui.press('enter')
            
            # 4. Restore windows? No, user wants to open the app.
            return True
            
        except Exception as e:
            logger.error(f"Error opening desktop icon: {e}", exc_info=True)
            return False

    def open_taskbar_icon(self, name):
        """Opens an app from the taskbar by name."""
        logger.info(f"Opening taskbar icon: {name}")
        
        # Redirect YouTube to open_app (which forces Edge)
        if "youtube" in name.lower():
            return self.open_app("youtube")

        try:
            # Fallback to simple open_app if inspection fails
            # But let's try Win+T (Focus Taskbar) -> Type Name?
            # Windows Taskbar doesn't support "Type to select" well.
            # So we will just use open_app as a robust fallback for now.
            logger.debug("Taskbar inspection difficult, falling back to open_app...")
            return self.open_app(name)
        except Exception as e:
            logger.error(f"Error opening taskbar icon: {e}", exc_info=True)
            return False

    def create_instant_meeting(self):
        """
        Creates a Google Meet instantly and saves the link to Notepad.

        Robust workflow:
        1. Open https://meet.google.com/new (Google auto-creates a room and
           redirects the address bar to meet.google.com/xxx-xxxx-xxx).
        2. POLL the address bar until that real room URL appears (the old
           code guessed a fixed 10s and often grabbed '/new' or nothing).
        3. Open Notepad and GENUINELY focus it via pywinauto before pasting
           (the old code pasted while the browser still had focus, so the
           link landed in the address bar instead).

        Returns the room URL string on success, or False.
        """
        logger.info("Creating Instant Google Meeting...")

        # Guard: if we just made one, don't spawn a duplicate.
        if self._last_meeting_url and (time.time() - self._last_meeting_time) < 45:
            logger.info("Reusing recently created meeting (dedupe).")
            return self._last_meeting_url

        try:
            pyperclip.copy("")  # clear clipboard so we can detect the new URL

            webbrowser.open("https://meet.google.com/new")
            logger.info("Waiting for Google to create the meeting room...")

            # --- Poll the address bar for the real room URL ---
            room_url = None
            room_re = re.compile(r"meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})", re.IGNORECASE)
            deadline = time.time() + 28
            while time.time() < deadline:
                time.sleep(2)
                pyautogui.hotkey('ctrl', 'l')   # focus address bar
                time.sleep(0.4)
                pyautogui.hotkey('ctrl', 'c')   # copy current URL
                time.sleep(0.4)
                try:
                    clip = pyperclip.paste().strip()
                except Exception:
                    clip = ""
                m = room_re.search(clip)
                if m:
                    room_url = "https://meet.google.com/" + m.group(1)
                    logger.info(f"Detected meeting room: {room_url}")
                    break

            pyautogui.press('escape')  # leave the address bar untouched

            if not room_url:
                logger.warning("Could not read the room URL; using whatever is in the address bar.")
                clip = ""
                try:
                    clip = pyperclip.paste().strip()
                except Exception:
                    pass
                room_url = clip if "meet.google.com" in clip else None

            if not room_url:
                return False

            # --- Save it to Notepad, with the browser NOT in focus ---
            self._write_to_notepad(f"Google Meet link:\r\n{room_url}\r\n")

            self._last_meeting_url = room_url
            self._last_meeting_time = time.time()
            return room_url

        except Exception as e:
            logger.error(f"Error creating instant meeting: {e}", exc_info=True)
            return False

    def _write_to_notepad(self, text):
        """
        Opens Notepad, RELIABLY brings it to the foreground (pywinauto
        set_focus — the piece that was missing), then pastes the text into
        the editor. No Ctrl+N (modern Notepad opens a new tab and loses focus).
        """
        self.open_app("notepad")
        time.sleep(2.5)

        # Bring Notepad genuinely to the front and give it keyboard focus.
        focused = False
        try:
            app = Application(backend="uia").connect(title_re=".*Notepad.*", timeout=8)
            win = app.top_window()
            if win.get_show_state() == 2:  # minimized
                win.restore()
            win.set_focus()
            time.sleep(0.8)
            focused = True
        except Exception as e:
            logger.warning(f"pywinauto Notepad focus failed ({e}); falling back to AppActivate.")
            self.focus_window("Notepad")
            time.sleep(0.8)

        if not focused:
            # Extra assurance for the fallback path: click the editor area.
            try:
                width, height = pyautogui.size()
                pyautogui.click(width // 2, height // 2)
                time.sleep(0.3)
            except Exception:
                pass

        # Paste via clipboard (reliable for URLs).
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        return True

    def select_all(self):
        """Selects all items in the active window (Ctrl+A)."""
        logger.info("Selecting all items...")
        try:
            pyautogui.hotkey('ctrl', 'a')
            return True
        except Exception as e:
            logger.error(f"Error selecting all: {e}")
            return False

    def empty_recycle_bin(self):
        """Empties the Recycle Bin by clicking the 'Empty Recycle Bin' button."""
        logger.info("Emptying Recycle Bin...")
        try:
            # 1. Click "Empty Recycle Bin" button
            # It's usually in the ribbon or context menu.
            # Let's try finding the button using UIA (click_element logic)
            if self.click_element("Empty Recycle Bin"):
                time.sleep(1)
                # 2. Confirm Dialog (Press Enter for "Yes")
                logger.info("Confirming deletion...")
                pyautogui.press('enter')
                return True
            else:
                logger.warning("Could not find 'Empty Recycle Bin' button.")
                return False
        except Exception as e:
            logger.error(f"Error emptying recycle bin: {e}", exc_info=True)
            return False

    def media_control(self, command):
        """
        Controls media playback (YouTube) in the active tab.
        Commands: next, previous, pause, play, forward, rewind, mute
        """
        logger.info(f"Media Control: {command}")
        try:
            if command == "next":
                pyautogui.hotkey('shift', 'n')
            elif command == "previous":
                pyautogui.hotkey('shift', 'p')
            elif command in ["pause", "play"]:
                pyautogui.press('k') # k toggles play/pause on YouTube
            elif command == "forward":
                pyautogui.press('l') # +10s
            elif command == "rewind":
                pyautogui.press('j') # -10s
            elif command == "mute":
                pyautogui.press('m')
            else:
                return False
            return True
        except Exception as e:
            logger.error(f"Error controlling media: {e}", exc_info=True)
            return False

    def write_code_in_notepad(self, files_list):
        """
        Opens Notepad and writes code for multiple files using tabs/pages.
        files_list: [{"name": "filename", "content": "code"}, ...]
        """
        logger.info(f"Writing {len(files_list)} files to Notepad...")
        try:
            # 1. Open Notepad
            self.open_app("notepad")
            time.sleep(2) # Wait for it to open
            
            for i, file_data in enumerate(files_list):
                name = file_data.get("name", "Untitled")
                content = file_data.get("content", "")
                
                # Header
                header = f"### FILE: {name} ###\n\n"
                full_content = header + content
                
                # 2. Paste Content
                pyperclip.copy(full_content)
                time.sleep(0.5)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.5)
                
                # 3. Create New Page (Ctrl+N) if not the last file
                if i < len(files_list) - 1:
                    logger.debug("Creating new page...")
                    pyautogui.hotkey('ctrl', 'n') # In modern Notepad, this might open a new window or tab depending on settings.
                    # If it opens a new window, that's fine.
                    time.sleep(1)
            
            return True
        except Exception as e:
            logger.error(f"Error writing to notepad: {e}", exc_info=True)
            return False

    def focus_window(self, title):
        """Focuses a window by title using PowerShell (Robust)."""
        logger.info(f"Focusing window: {title}")
        try:
            cmd = f"powershell (New-Object -ComObject WScript.Shell).AppActivate('{title}')"
            subprocess.run(cmd, shell=True)
            time.sleep(0.5)
            return True
        except Exception as e:
            logger.error(f"Error focusing window: {e}", exc_info=True)
            return False

    def read_specific_chat_area(self):
        """
        Reads text from WhatsApp by selecting all and copying to clipboard.
        Uses robust window focusing and clicking to ensure success.
        """
        logger.info("Reading chat area (Clipboard Strategy)...")
        try:
            # 1. Focus Window (Robust)
            self.focus_window("WhatsApp")
            time.sleep(0.5)
            
            # 2. Maximize (Ensure consistent coordinates)
            pyautogui.hotkey('win', 'up')
            time.sleep(0.5)
            
            # 3. Clear Clipboard
            import pyperclip
            pyperclip.copy("")
            
            # 4. Click in Message List (Center of Chat Pane)
            width, height = pyautogui.size()
            click_x = int(width * 0.6) 
            click_y = int(height * 0.5)
            
            logger.debug(f"Clicking at ({click_x}, {click_y})...")
            pyautogui.click(click_x, click_y)
            time.sleep(0.5)
            
            # 5. Focus Adjustment (Tab)
            # Sometimes focus is on a specific message or input box.
            # Pressing Tab might cycle to the list container.
            # Or Shift+Tab from input box.
            # Let's try clicking, then Esc (to clear selection/focus), then Ctrl+A
            pyautogui.press('esc')
            time.sleep(0.2)
            
            # 6. Select All (Ctrl+A)
            logger.debug("Sending Ctrl+A...")
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.5)
            
            # 7. Copy (Ctrl+C)
            logger.debug("Sending Ctrl+C...")
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(1.0) # Wait for copy
            
            # 8. Get Content
            # 8. Get Content with Retry
            content = ""
            for _ in range(3):
                try:
                    content = pyperclip.paste().strip()
                    break
                except Exception:
                    time.sleep(0.5)
            
            logger.debug(f"Clipboard Content Length: {len(content)}")
            
            # Fallback: If empty, try clicking slightly higher
            if not content:
                logger.debug("Content empty. Trying higher click...")
                pyautogui.click(click_x, click_y - 200)
                time.sleep(0.5)
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.5)
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(1.0)
                content = pyperclip.paste().strip()
                logger.debug(f"Retry Content Length: {len(content)}")
            
            # 9. Deselect (Click again)
            pyautogui.click(click_x, click_y)
            
            return content

        except Exception as e:
            logger.error(f"Error reading chat area: {e}", exc_info=True)
            return ""

    def capture_chat_screenshot(self):
        """
        Captures a screenshot of the WhatsApp Chat Pane (Right side).
        Returns the path to the saved image.
        """
        logger.info("Capturing chat screenshot...")
        try:
            # 1. Connect and Get Window
            app = Application(backend="uia").connect(title_re=".*WhatsApp.*", timeout=10)
            win = app.top_window()
            
            if win.get_show_state() == 2:
                win.restore()
            win.set_focus()
            time.sleep(0.5)
            
            # Get Window Rect
            rect = win.rectangle()
            win_left = rect.left
            win_top = rect.top
            win_width = rect.width()
            win_height = rect.height()
            
            # Calculate Chat Pane Region
            # Start: 35% from left
            # End: 100% width
            # Top: 100px from top (header)
            # Bottom: 100px from bottom (input)
            
            region_left = win_left + int(win_width * 0.35)
            region_top = win_top + 80
            region_width = int(win_width * 0.65) - 20 # Slight padding
            region_height = win_height - 180 # Header + Input
            
            # Screenshot
            screenshot_path = os.path.join(os.getcwd(), "chat_screenshot.png")
            pyautogui.screenshot(screenshot_path, region=(region_left, region_top, region_width, region_height))
            
            logger.info(f"Screenshot saved to: {screenshot_path}")
            return screenshot_path
        
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}", exc_info=True)
            return None
