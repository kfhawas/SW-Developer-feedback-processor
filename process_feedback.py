"""Entry point kept at the original path, so existing usage still works:

python process_feedback.py file1.csv file2.csv
"""

import sys

from feedback_processor.cli import main

if __name__ == "__main__":
    sys.exit(main())
