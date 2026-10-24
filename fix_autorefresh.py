from pathlib import Path
p = Path("app.py")
src = p.read_text(encoding="utf-8")

# 1. Add import at top (after existing imports)
if "from streamlit_autorefresh import st_autorefresh" not in src:
    old_imp = "import streamlit as st"
    new_imp = "import streamlit as st\nfrom streamlit_autorefresh import st_autorefresh"
    if old_imp in src:
        src = src.replace(old_imp, new_imp, 1)
        print("[OK] Import added")

# 2. Add autorefresh call after page config
if "st_autorefresh(" not in src:
    old_pc = 'st.set_page_config(page_title="Nifty Agent"'
    marker = src.find(old_pc)
    if marker != -1:
        end_of_pc = src.find("\n", src.find(")", marker)) + 1
        autorefresh_call = '\n# Auto-refresh every 60 seconds\nst_autorefresh(interval=60000, key="auto_refresh")\n'
        src = src[:end_of_pc] + autorefresh_call + src[end_of_pc:]
        print("[OK] st_autorefresh call added")

# 3. Remove the script-tag approach (doesn't work reliably)
old_script = '''# Auto-refresh every 60s
st.markdown("""
<script>
setTimeout(function(){ window.location.reload(); }, 60000);
</script>
""", unsafe_allow_html=True)'''

if old_script in src:
    src = src.replace(old_script, "# Auto-refresh handled by st_autorefresh at top", 1)
    print("[OK] Old script-tag approach removed")

p.write_text(src, encoding="utf-8")
print()
print("=" * 50)
print("APP.PY FIXED FOR AUTO-REFRESH")
print("=" * 50)
