import sys
import os

# mini-cloud/ কে Python path-এ যোগ করা — relative import কাজ করার জন্য
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == '__main__':
    print("\n Mini Cloud System — Auth Module")
    print(" Running at: http://0.0.0.0:5001")
    print(" API Base:   http://localhost:5001/api/v1/auth\n")
    # debug=True: file change হলে auto-restart, full error traceback দেখায়
    app.run(host='0.0.0.0', port=5001, debug=True)
