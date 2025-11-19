# app.py
import streamlit as st
from tool import (
    read_requirements, read_courses, calculate_credits,
    cascade_allocation, compute_bundle,
    PROG_BCE_MIN, GRAD_BCDE_MIN
)

st.title("単ナビ")

# 表示名
DISPLAY = {
    "A":  "A",
    "B0": "B(専門基礎科目)",
    "B1": "B(専門応用科目)",
    "C":  "C",
    "D":  "D",
    "E":  "E",
}
def disp(cat: str) -> str:
    return DISPLAY.get(cat, cat)

# モード選択
mode_label = st.radio("判定モード", ("進級", "卒業"))
mode = "p" if mode_label == "進級" else "g"
req_file = "requirements2.txt" if mode == "p" else "requirements1.txt"

# 学籍番号（任意）
student_id = st.text_input("学籍番号（任意）")

# データ読み込み
required = read_requirements(req_file)
courses  = read_courses()

st.markdown("---")
st.header("取得済み講義を選択")

# 講義選択UI
earned_courses = {}
for cat in ["A", "B0", "B1", "C", "D", "E"]:
    lst = courses.get(cat, [])
    st.subheader(f"{disp(cat)}区分")
    if not lst:
        st.caption("登録講義なし")
        earned_courses[cat] = []
        continue
    opts = [name for name, _ in lst]
    selected = st.multiselect(f"{disp(cat)}区分の講義を選択", options=opts, key=f"ms_{cat}")
    earned_courses[cat] = [(name, cr) for name, cr in lst if name in selected]

if st.button("結果を表示"):
    # 集計 → 段階的充当 → 合算要件
    earned = calculate_credits(earned_courses)
    cas = cascade_allocation(required, earned)
    bundle_label, bundle_total, bundle_need, bundle_ok = compute_bundle(mode, earned, cas)

    st.markdown("---")
    st.header("結果")

    # A, B0, B1, C, D, E
    for cat in ["A", "B0", "B1", "C", "D", "E"]:
        need = required.get(cat, 0)
        got  = earned.get(cat, 0)

        if cat == "B0":
            remain = max(0, need - got)
            st.write(f"B(専門基礎科目): 必要 {need} / 取得 {got} / 残り {remain} ・ 余剰 {cas['b0_surplus']}")

        elif cat == "B1":
            if cas["b1_short"] > 0:
                st.write(
                    f"B(専門応用科目): 必要 {need} / 取得 {got} / B(専門基礎科目)からの充当後 {cas['b1_after_fill']} / 残り {cas['b1_short']}"
                )
            else:
                st.write(
                    f"B(専門応用科目): 必要 {need} / 取得 {got} / 残り 0 ・ 合算に用いるB(専門応用科目)余剰 {cas['b1_surplus_for_bundle']}"
                )

        elif cat == "C":
            st.write(f"C区分: 取得 {got}")

        else:
            remain = max(0, need - got)
            st.write(f"{disp(cat)}区分: 必要 {need} / 取得 {got} / 残り {remain}")

    st.markdown("---")
    st.subheader("合算要件の判定")
    if mode == "p":
        st.caption(f"基準：B(専門応用科目)余剰分 + C + E ≥ {PROG_BCE_MIN}")
    else:
        st.caption(f"基準：B(専門応用科目)余剰分 + C + D + E ≥ {GRAD_BCDE_MIN}")

    passed_text = "達成" if bundle_ok else "未達成"
    st.write(f"{bundle_label}: 合計 {bundle_total} / 基準 {bundle_need} → {passed_text}")

    # 未取得講義
    st.markdown("---")
    st.subheader("未取得の講義")
    any_missing = False
    for cat in ["A", "B0", "B1", "C", "D", "E"]:
        lst = courses.get(cat, [])
        taken = {n for n, _ in earned_courses.get(cat, [])}
        remaining = [n for n, _ in lst if n not in taken]
        if remaining:
            any_missing = True
            st.markdown(f"{disp(cat)}区分")
            for n in remaining:
                st.write(f"- {n}")
    if not any_missing:
        st.write("未取得の講義はありません")
