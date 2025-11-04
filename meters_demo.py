import time
import usb.backend.libusb1 as libusb1
from usb.core import find as usb_find
from pyrow import pyrow

# Tell PyUSB exactly where libusb is
LIBUSB_PATH = "/opt/homebrew/lib/libusb-1.0.dylib"  # adjust if brew --prefix differs
backend = libusb1.get_backend(find_library=lambda x: LIBUSB_PATH)
if backend is None:
    raise SystemExit("libusb backend not found. Check LIBUSB_PATH.")

# Concept2 vendor id = 0x17A4
dev = next(iter(usb_find(find_all=True, idVendor=0x17A4, backend=backend)), None)
if dev is None:
    raise SystemExit("No Concept2 PM detected. Wake the PM5 and check USB.")

erg = pyrow.PyErg(dev)
print("Connected. Printing meters each second. Ctrl+C to stop.")
while True:
    m = erg.get_monitor()  # dict includes 'distance' in meters
    print(int(m["distance"]))
    time.sleep(1)
