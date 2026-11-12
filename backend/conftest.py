# Puts backend/ on sys.path so `app` imports work when pytest runs from backend/.
# Tracing is forced off so tests never touch the network or a running Phoenix.
import os

os.environ["SDL_TRACING"] = "off"
