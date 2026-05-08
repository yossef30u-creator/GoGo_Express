import os

def list_files(startpath):
    for root, dirs, files in os.walk(startpath):
        # מתעלם מתיקיות מערכת וסביבה וירטואלית כדי שהרשימה תהיה נקייה
        dirs[:] = [d for d in dirs if d not in ['.venv', 'venv', '__pycache__', '.git', '.idea', '.vscode']]
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            # לא מדפיס את הקובץ הזה עצמו
            if f != 'list_my_project.py':
                print(f'{subindent}{f}')

if __name__ == "__main__":
    print("--- מבנה הפרויקט שלי ---")
    list_files('.')
    print("-----------------------")
