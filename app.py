import streamlit as st
import pandas as pd
import pdfplumber
import io
from datetime import datetime
import re
import calendar

def extract_text_from_pdf(pdf_file):
    """PDFからテキストを抽出"""
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def parse_suica_data(text, user_name="田中太郎", valid_stations=None,
                    target_year=None, target_month=5, exclude_keywords=None):
    """Suica利用履歴テキストを解析してDataFrameに変換"""
    if valid_stations is None:
        valid_stations = ["五反田"]

    if exclude_keywords is None:
        exclude_keywords = ["物販", "ｶｰﾄﾞ", "モバイル"]

    if target_year is None:
        target_year = datetime.now().year

    lines = text.strip().split('\n')
    data = []

    for line in lines:
        line = line.strip()

        # Suica利用記録の形式を検出: "05 01 入 戸越銀座 出 東急五反 -140"
        # 正規表現で月日と記録を同時に抽出
        suica_pattern = r'^(\d{2})\s+(\d{2})\s+(.+?)\s+(-\d{1,3}(?:,\d{3})*)$'
        match = re.match(suica_pattern, line)

        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            record = match.group(3)
            amount_str = match.group(4)

            # 指定した年月のデータのみを対象とする
            if month != target_month:
                continue

            # 除外キーワードをチェック
            if any(keyword in record for keyword in exclude_keywords):
                continue

            # 有効な駅・バスかチェック
            is_valid = False

            # バス利用かどうかを判定（「バス」を含む場合）
            is_bus = "バス" in record

            if is_bus:
                # バスの場合：バス事業者が指定駅に含まれているかチェック
                # record内からバス事業者名を抽出
                bus_companies = [station for station in valid_stations if "バス" in station]
                is_valid = any(bus_company in record for bus_company in bus_companies)
            elif "入" in record and "出" in record:
                # 駅間移動の場合：起点または終点のいずれかが指定駅に含まれているかチェック
                parts = record.split()
                from_station = ""
                to_station = ""

                # 「入」の次の要素が起点駅、「出」の次の要素が終点駅
                for i, part in enumerate(parts):
                    if part == "入" or part == "＊入" and i + 1 < len(parts):
                        from_station = parts[i + 1]
                    elif part == "出" and i + 1 < len(parts):
                        to_station = parts[i + 1]

                # 起点または終点のいずれかが指定駅に含まれているかチェック（バス事業者は除外）
                station_list = [station for station in valid_stations if "バス" not in station]
                from_valid = any(station in from_station for station in station_list)
                to_valid = any(station in to_station for station in station_list)

                # AND条件：起点と終点の両方が指定駅に含まれている必要がある
                is_valid = from_valid and to_valid
            else:
                # その他の場合（通常はないが念のため）
                is_valid = any(station in record for station in valid_stations)

            if is_valid:
                # 金額を数値に変換
                amount = int(amount_str.replace('-', '').replace(',', ''))

                # 摘要を生成
                if is_bus:
                    # バス利用の場合、事業者名を抽出
                    bus_companies = [station for station in valid_stations if "バス" in station and station in record]
                    if bus_companies:
                        summary = bus_companies[0]  # 最初に見つかった事業者名を使用
                    else:
                        summary = "バス"  # バス事業者が見つからない場合のフォールバック
                elif "入" in record and "出" in record:
                    # 駅間移動の場合
                    parts = record.split()
                    from_station = ""
                    to_station = ""

                    # 「入」の次の要素が起点駅、「出」の次の要素が終点駅
                    for i, part in enumerate(parts):
                        if part == "入" or part == "＊入" and i + 1 < len(parts):
                            from_station = parts[i + 1]
                        elif part == "出" and i + 1 < len(parts):
                            to_station = parts[i + 1]

                    if from_station and to_station:
                        summary = f"{from_station} -> {to_station}"
                    else:
                        summary = "移動"
                else:
                    summary = "交通費"

                data.append({
                    "月": f"{month:02d}",
                    "日": f"{day:02d}",
                    "氏名": user_name,
                    "支払先": "SUICA",
                    "摘要": summary,
                    "勘定科目名": "交通費",
                    "金額": amount
                })

    return pd.DataFrame(data)

def get_weekends_for_month(year, month):
    """指定された年月の土日を取得"""
    weekends = []

    # その月の日数を取得
    days_in_month = calendar.monthrange(year, month)[1]

    for day in range(1, days_in_month + 1):
        # 曜日を取得 (0=月曜日, 6=日曜日)
        weekday = calendar.weekday(year, month, day)

        # 土曜日(5)または日曜日(6)の場合
        if weekday >= 5:
            weekends.append(day)

    return weekends

def filter_weekdays(df, target_year, target_month):
    """指定された年月の土日を除外"""
    if len(df) == 0:
        return df

    # 動的に土日を計算
    weekends = get_weekends_for_month(target_year, target_month)

    try:
        # 「日」列から数字のみを抽出
        df_copy = df.copy()

        # 各値を個別に処理して数字のみを抽出
        day_numbers = []
        for day_value in df_copy['日']:
            # 文字列に変換
            day_str = str(day_value)
            # 数字のみを抽出
            numbers = re.findall(r'\d+', day_str)
            if numbers:
                day_numbers.append(int(numbers[0]))
            else:
                # 数字が見つからない場合は1を設定（平日として扱う）
                day_numbers.append(1)

        df_copy['日_数値'] = day_numbers

        # 土日を除外
        filtered_df = df_copy[~df_copy['日_数値'].isin(weekends)].drop(columns=['日_数値'])

        return filtered_df

    except Exception as e:
        st.error(f"日付の変換でエラーが発生しました: {str(e)}")
        return df

def main():
    st.set_page_config(
        page_title="Suica交通費申請CSV変換ツール",
        page_icon="🚊",
        layout="wide"
    )

    st.title("🚊 Suica交通費申請CSV変換ツール")
    st.markdown("---")

    # セッション状態の初期化
    if 'pdf_text' not in st.session_state:
        st.session_state.pdf_text = None
    if 'uploaded_filename' not in st.session_state:
        st.session_state.uploaded_filename = None

    # サイドバーで設定
    with st.sidebar:
        st.header("⚙️ 設定")

        user_name = st.text_input("氏名", value="田中太郎")

        st.subheader("対象駅・交通機関")
        default_stations = ["五反田"]
        stations_text = st.text_area(
            "対象駅・交通機関（1行に1つずつ入力）",
            value="\n".join(default_stations),
            height=100,
            help="駅名やバス事業者名（例：東急バス）を入力してください"
        )
        valid_stations = [station.strip() for station in stations_text.split('\n') if station.strip()]

        st.subheader("対象期間")
        col1, col2 = st.columns(2)
        with col1:
            target_year = st.number_input("対象年", min_value=2020, max_value=2030, value=datetime.now().year)
        with col2:
            target_month = st.number_input("対象月", min_value=1, max_value=12, value=5)

        # 土日除外設定
        st.subheader("土日除外設定")
        exclude_weekends = st.checkbox("土日を除外", value=True, help=f"{target_year}年{target_month}月の土日を自動的に除外します")

        # 除外キーワード設定
        st.subheader("除外キーワード")
        default_exclude_keywords = ["物販", "ｶｰﾄﾞ", "モバイル"]
        exclude_keywords_text = st.text_area(
            "除外キーワード（1行に1つずつ入力）",
            value="\n".join(default_exclude_keywords),
            height=80,
            help="ここに入力したキーワードを含む記録は除外されます"
        )
        exclude_keywords = [kw.strip() for kw in exclude_keywords_text.split('\n') if kw.strip()]

        # 設定のプレビュー
        with st.expander("現在の設定"):
            st.write("**対象駅・交通機関:**", valid_stations)
            st.write("**対象期間:**", f"{target_year}年{target_month}月")
            st.write("**土日除外:**", exclude_weekends)
            st.write("**除外キーワード:**", exclude_keywords)

    # メイン画面
    col1, col2 = st.columns([1, 1])

    with col1:
        st.header("📄 PDFアップロード")

        uploaded_file = st.file_uploader(
            "Suica利用履歴PDFを選択",
            type=['pdf']
        )

        # PDFテキストの取得（新規アップロードまたは既存データ使用）
        text_to_process = None

        if uploaded_file is not None:
            # 新しいファイルがアップロードされた場合
            if st.session_state.uploaded_filename != uploaded_file.name:
                try:
                    with st.spinner("PDFを解析中..."):
                        text_to_process = extract_text_from_pdf(uploaded_file)
                        st.session_state.pdf_text = text_to_process
                        st.session_state.uploaded_filename = uploaded_file.name
                except Exception as e:
                    st.error(f"❌ PDFの読み込みエラー: {str(e)}")
                    text_to_process = None
            else:
                # 既にアップロード済みのファイルの場合
                text_to_process = st.session_state.pdf_text
        elif st.session_state.pdf_text is not None:
            # ファイルアップローダーは空だが、セッションにデータがある場合
            text_to_process = st.session_state.pdf_text

        # データ処理
        df = pd.DataFrame()

        if text_to_process is not None:
            try:
                # データ変換
                with st.spinner("データを変換中..."):
                    df = parse_suica_data(text_to_process, user_name, valid_stations, target_year, target_month, exclude_keywords)

                    if exclude_weekends:
                        df = filter_weekdays(df, target_year, target_month)

                if len(df) > 0:
                    st.success(f"✅ {len(df)}件のデータを抽出")
                else:
                    st.warning("⚠️ 対象データが見つかりません")

            except Exception as e:
                st.error(f"❌ 処理エラー: {str(e)}")
                df = pd.DataFrame()

    with col2:
        st.header("📊 変換結果")

        if len(df) > 0:
            # データ表示
            st.dataframe(df, use_container_width=True)

            # 合計金額
            total_amount = df['金額'].sum()
            st.metric("💰 合計金額", f"{total_amount:,}円")

            # CSV生成
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_data = csv_buffer.getvalue()

            # ダウンロードボタン
            current_date = datetime.now().strftime("%Y%m%d")
            filename = f"交通費申請_{current_date}.csv"

            st.download_button(
                label="📥 CSVファイルをダウンロード",
                data=csv_data,
                file_name=filename,
                mime='text/csv',
                type="primary"
            )

            # プレビュー用CSV表示
            with st.expander("CSVプレビュー"):
                st.code(csv_data, language="csv")

        elif st.session_state.pdf_text is not None:
            st.info("設定を調整すると自動的に再計算されます")
        else:
            st.info("PDFファイルをアップロードしてください")

    # フッター
    st.markdown("---")
    st.markdown(
        """
        **使い方:**
        1. 左側でPDFファイルをアップロード
        2. 必要に応じて設定を調整（自動的に再計算されます）
        3. 右側で結果を確認してCSVをダウンロード

        **注意事項:**
        - モバイルSuicaの利用履歴PDFに対応
        - 指定した駅・交通機関の起点・終点を持つ移動のみが対象
        - 土日の利用は除外可能
        - 一度アップロードしたファイルは設定変更時に再利用されます
        """
    )

if __name__ == "__main__":
    main()
