import streamlit as st
import pandas as pd
import os
import re
from tool import (
    read_requirements, read_courses, calculate_credits,
    cascade_allocation, compute_bundle,  # ← 充当＆合算を利用
    PROG_BCE_MIN, GRAD_BCDE_MIN          # ← 基準値を表示に使用
)

st.set_page_config(page_title="単位管理ツール", layout="wide")
st.title(" 単ナビ")

# 表示名（E区分はUIから除外）
DISPLAY = {
    "A":  "A(必修科目)",
    "B0": "B(専門基礎科目)",
    "B1": "B(専門応用科目)",
    "C":  "C(選択科目)",
    "D":  "D(特殊選択科目)",
}
def disp(cat: str) -> str:
    return DISPLAY.get(cat, cat)

# ------------------------------
# 進級 or 卒業
# ------------------------------
mode = st.radio("要件を選択してください", ["進級要件", "卒業要件"])
req_file = "requirements2.txt" if mode == "進級要件" else "requirements1.txt"
required = read_requirements(req_file)
mode_code = "p" if mode == "進級要件" else "g"   # ← tool.compute_bundle 用

# ------------------------------
# 学籍番号 & パスワード入力
# ------------------------------
student_id = st.text_input("学籍番号を入力してください", placeholder="例: 1234567")
password   = st.text_input("パスワードを入力してください", type="password")

# ------------------------------
# 講義一覧読み込み
# ------------------------------
courses = read_courses("courses.txt")

# ------------------------------
# 保存データ読み込み（パスワード付き）
# ------------------------------
loaded_taken = {}          # {区分: [講義名, ...]}
file_has_password = False  # ファイルにPWD行があるか
password_ok = False        # 認証が通ったか

if student_id:
    filename = f"taken_{student_id}.txt"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if lines and lines[0].startswith("PWD "):
            file_has_password = True
            stored_pw = lines[0].strip()[4:]
            if not password:
                st.warning("この学籍番号にはパスワードが設定されています。パスワードを入力してください。")
            elif password != stored_pw:
                st.error("パスワードが正しくありません。")
            else:
                password_ok = True
                for line in lines[1:]:
                    parts = line.strip().rsplit(" ", 2)
                    if len(parts) != 3:
                        continue
                    cat, name, credit = parts
                    loaded_taken.setdefault(cat, []).append(name)
                st.success(" 保存されたデータを読み込みました！")
        else:
            if not password:
                st.info("この学籍番号にはまだパスワードが設定されていません。今回入力するパスワードで新規設定されます。")
            else:
                password_ok = True
                for line in lines:
                    parts = line.strip().rsplit(" ", 2)
                    if len(parts) != 3:
                        continue
                    cat, name, credit = parts
                    loaded_taken.setdefault(cat, []).append(name)
                st.info("旧形式のデータを読み込みました。このパスワードで新しく保護されます。")
    else:
        st.info(" 保存データはありません（初回利用と思われます）。")

# ------------------------------
# 取得済みの講義選択
# ------------------------------
st.subheader("取得済み講義を選択してください")

earned_courses = {}

# A / B0 / B1 / C / D のみ（EはUI非表示）
for cat in ["A", "B0", "B1", "C", "D"]:
    subject_list = courses.get(cat, [])
    st.markdown(f"### {disp(cat)}")
    if not subject_list:
        st.caption("登録講義なし")
        earned_courses[cat] = []
        continue

    saved_names = set(loaded_taken.get(cat, [])) if password_ok else set()

    # 1) 保存済みから取り消し
    if saved_names:
        st.caption("すでに保存されている取得講義（取り消したいものがあれば選択）")
        cancel_selected = st.multiselect(
            f"{disp(cat)}で取得済みとして登録されている講義（取り消すものを選択）",
            sorted(saved_names),
            key=f"cancel_{cat}"
        )
        cancel_set = set(cancel_selected)
    else:
        cancel_set = set()

    kept_names = saved_names - cancel_set

    # 2) 新規で取得した講義
    st.caption("新たに取得した講義があれば選択してください")
    # ラベル→(name, credit) で安全に復元（講義名に全角カッコがあってもOK）
    label_map = {}
    for name, credit in subject_list:
        if name in saved_names:
            continue
        label = f"{name}（{credit}単位）"
        label_map[label] = (name, credit)

    selected_new = st.multiselect(
        f"{disp(cat)}で新たに取得した講義を選択",
        list(label_map.keys()),
        key=f"new_{cat}"
    )

    # 3) 現時点の取得済み
    current_taken = []
    for name, credit in subject_list:
        if name in kept_names:
            current_taken.append((name, credit))
    for label in selected_new:
        name, credit = label_map[label]
        current_taken.append((name, credit))

    earned_courses[cat] = current_taken

# ------------------------------
# 結果表示 & 保存
# ------------------------------
if st.button("結果を表示"):
    if not student_id:
        st.error("学籍番号を入力してください。")
    elif not password:
        st.error("パスワードを入力してください。")
    elif file_has_password and not password_ok:
        st.error("正しいパスワードが入力されていないため、結果の表示・保存はできません。")
    else:
        # 1) 単位集計
        earned = calculate_credits(earned_courses)

        st.subheader(" 結果")
        rows = []
        for cat in ["A", "B0", "B1", "C", "D"]:
            need = required.get(cat, 0)
            got = earned.get(cat, 0)
            remain = max(0, need - got)
            rows.append({"区分": disp(cat), "必要": need, "取得": got, "残り": remain})
        st.table(pd.DataFrame(rows))

        # 2) B(基礎)→B(応用) 充当 と 合算要件
        cas = cascade_allocation(required, earned)
        bundle_label, bundle_total, bundle_need, bundle_ok = compute_bundle(mode_code, earned, cas)

        st.markdown("---")
        st.subheader("Bの充当状況")
        # B(専門基礎科目)
        need_b0 = required.get("B0", 0)
        got_b0  = earned.get("B0", 0)
        st.write(f"・B(専門基礎科目)：必要 {need_b0} / 取得 {got_b0} / 余剰 {cas['b0_surplus']}")

        # B(専門応用科目)
        need_b1 = required.get("B1", 0)
        got_b1  = earned.get("B1", 0)
        if cas["b1_short"] > 0:
            st.write(f"・B(専門応用科目)：必要 {need_b1} / 取得 {got_b1} / B(基礎)充当後 {cas['b1_after_fill']} / 残り {cas['b1_short']}")
        else:
            st.write(f"・B(専門応用科目)：必要 {need_b1} / 取得 {got_b1} / 残り 0 ・ 合算に用いるB(専門応用科目)余剰 {cas['b1_surplus_for_bundle']}")

        st.markdown("---")
        st.subheader("合算要件の判定")
        if mode_code == "p":
            st.caption(f"基準：B(専門応用科目)余剰分 + C + E ≥ {PROG_BCE_MIN}")
            label_text = "B(専門応用科目)余剰分 + C + E"
        else:
            st.caption(f"基準：B(専門応用科目)余剰分 + C + D + E ≥ {GRAD_BCDE_MIN}")
            label_text = "B(専門応用科目)余剰分 + C + D + E"

        passed_text = "達成" if bundle_ok else "未達成"
        st.write(f"{label_text}: 合計 {bundle_total} / 基準 {bundle_need} → {passed_text}")

        # 3) 詳細（未取得）
        st.markdown("---")
        st.subheader("詳細")
        for cat in ["A", "B0", "B1", "C", "D"]:
            if cat not in courses:
                continue
            taken_now = [name for name, _ in earned_courses.get(cat, [])]
            remaining = [name for name, _ in courses[cat] if name not in set(taken_now)]
            st.markdown(f"#### {disp(cat)}")
            st.write(f"取得済み: {', '.join(taken_now) if taken_now else 'なし'}")
            st.write(f"未取得: {', '.join(remaining) if remaining else 'すべて取得済み'}")

        # 4) 保存（先頭行にPWDを書いて保護）
        filename = f"taken_{student_id}.txt"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"PWD {password}\n")
                for cat, subs in earned_courses.items():
                    for name, credit in subs:
                        f.write(f"{cat} {name} {credit}\n")
            st.success(f" データを保存しました！（{filename}）")
        except Exception as e:
            st.error(f"データ保存中にエラーが発生しました: {e}")
