import speech_recognition as sr
from seetha.logger import setup_logger
import time

logger = setup_logger()

class SeethaEars:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        
        # Hardware Compatibility: Find best mic
        self.device_index = self._find_best_microphone()
        
        if self.device_index is not None:
            logger.info(f"Selected Best Microphone Index: {self.device_index}")
        else:
            logger.info("Using System Default Microphone")

        self.calibrate()

    def _get_microphone(self):
        """Creates a fresh microphone instance to prevent context errors."""
        # Enterprise Fix: Always create a new instance to ensure clean stream state
        if self.device_index is not None:
             return sr.Microphone(device_index=self.device_index)
        return sr.Microphone()

    def _find_best_microphone(self):
        """
        Scans for the best available microphone.
        Enterprise Strategy: 
        1. Prefer 'Headset' or 'Microphone' explicitly (Reliable hardware).
        2. Avoid 'Virtual' or 'Cable' inputs which often cause silence.
        3. Default to System Default (None) if no clear winner.
        """
        try:
            mics = sr.Microphone.list_microphone_names()
            logger.info(f"Available Audio Devices: {mics}")
            
            # Keywords to prioritize (High Quality)
            high_priority = ["headset", "jabra", "plantronics", "logitech", "sennheiser"]
            
            # Keywords to AVOID (Virtual Cables, Monitors)
            avoid = ["line", "stereo mix", "virtual", "monitor", "display", "nvidia"]
            
            for index, name in enumerate(mics):
                name_lower = name.lower()
                
                # Check for high priority matches
                if any(k in name_lower for k in high_priority):
                     logger.info(f"Selected High-Priority Mic: {name} (Index {index})")
                     return index
                     
            # If no high priority, scan for generic "microphone" but exclude bad ones
            for index, name in enumerate(mics):
                name_lower = name.lower()
                if "microphone" in name_lower and not any(k in name_lower for k in avoid):
                    logger.info(f"Selected Generic Mic: {name} (Index {index})")
                    return index
            
            logger.info("No specific hardware mic found. Using System Default.")
            return None # Fallback to default
        except Exception as e:
            logger.error(f"Error finding microphone: {e}")
            return None

    def calibrate(self):
        """Calibrates the microphone for ambient noise."""
        try:
            # Use fresh mic instance
            mic = self._get_microphone()
            with mic as source:
                logger.info("Calibrating microphone for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

                # Enterprise Grade: Dynamic Thresholding
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.dynamic_energy_adjustment_damping = 0.15
                self.recognizer.dynamic_energy_ratio = 1.5
                self.recognizer.pause_threshold = 0.8

                logger.info(f"Microphone calibrated. Initial Threshold: {self.recognizer.energy_threshold}")
        except Exception as e:
            logger.error(f"Error during calibration: {e}")
            # Robustness: the preferred mic (often a Bluetooth headset)
            # can fail to open. Fall back to the system default mic so
            # listening still works instead of dying silently.
            if self.device_index is not None:
                logger.warning("Selected mic failed. Falling back to system default microphone.")
                self.device_index = None
                try:
                    with self._get_microphone() as source:
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        logger.info("Default microphone calibrated successfully.")
                except Exception as e2:
                    logger.error(f"Default mic calibration also failed: {e2}")

    def listen(self):
        """Listens for audio and converts it to text."""
        try:
            # Use fresh mic instance
            mic = self._get_microphone()
            with mic as source:
                try:
                    # Enterprise Grade: Optimized Timeout
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    
                    text = self.recognizer.recognize_google(audio)
                    logger.info(f"User said: {text}")
                    return text
                except sr.WaitTimeoutError:
                    return None
                except sr.UnknownValueError:
                    return None
                except sr.RequestError as e:
                    logger.error(f"Network Error (Speech API): {e}")
                    return None
        except OSError as e:
            logger.error(f"Microphone HW Error: {e}")
            # If a specific device keeps failing, drop to system default
            # so the listening loop recovers on the next iteration.
            if self.device_index is not None:
                logger.warning("Switching to system default microphone after hardware error.")
                self.device_index = None
            time.sleep(1) # Prevent CPU spin
            return None
        except Exception as e:
            logger.error(f"Critical Listening Error: {e}", exc_info=True)
            return None
