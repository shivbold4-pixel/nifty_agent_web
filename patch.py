from pathlib import Path

p = Path("app.py")
src = p.read_text(encoding="utf-8")

# --- Patch 1: Store df in session state ---
target1 = "st.session_state.uploaded_seen.add(fingerprint)"
replacement1 = (
    "st.session_state.uploaded_seen.add(fingerprint)\n"
    "            st.session_state.df = df"
)
if target1 in src and "st.session_state.df = df" not in src:
    src = src.replace(target1, replacement1)
    print("[OK] df stored in session state")
else:
    print("[SKIP] Patch 1 already applied or target not found")

# --- Patch 2: Guard the preview block ---
target2 = (
    'with st.expander("Parsed data preview (first 5 rows)", expanded=False):\n'
    '        st.dataframe(df.head(5), use_container_width=True, hide_index=True)\n'
    '        st.caption(f"Parsed {len(df)} rows, {len(df.columns)} columns")'
)
replacement2 = (
    'with st.expander("Parsed data preview (first 5 rows)", expanded=False):\n'
    '        if "df" in st.session_state:\n'
    '            st.dataframe(st.session_state.df.head(5), use_container_width=True, hide_index=True)\n'
    '            st.caption(f"Parsed {len(st.session_state.df)} rows, {len(st.session_state.df.columns)} columns")\n'
    '        else:\n'
    '            st.info("Upload a file to see the preview.")'
)
if target2 in src and 'st.session_state.df.head' not in src:
    src = src.replace(target2, replacement2)
    print("[OK] Preview block guarded")
else:
    print("[SKIP] Patch 2 already applied or target not found")

p.write_text(src, encoding="utf-8")
print("PATCHED SUCCESSFULLY")
