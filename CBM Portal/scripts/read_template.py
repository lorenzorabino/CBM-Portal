import traceback
p = r"C:\Users\Angel\Documents\L.A\OneDrive\Cbmportal\cbm_monday_lite_web\simple-web-portal\app\templates\planner_entries.html"
print('Path:', p)
try:
    with open(p, 'rb') as f:
        b = f.read(512)
        print('Read bytes:', type(b), len(b))
        print(repr(b[:200]))
except Exception:
    print('rb open error:')
    traceback.print_exc()

try:
    with open(p, 'r', encoding='utf-8') as f:
        s = f.read(512)
        print('Read str length:', len(s))
        print(s[:400])
except Exception:
    print('text open error:')
    traceback.print_exc()
