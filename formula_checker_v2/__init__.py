import logging
import azure.functions as func
import pandas as pd
import io
import base64
import json

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ログ出力を追加してリクエストの詳細を確認
        logging.info(f"Headers: {req.headers}")
        logging.info(f"Body length: {len(req.get_body())}")
        logging.info(f"Raw body: {req.get_body().decode('utf-8')}")

        # JSONデータの取得
        data = req.get_json()
        m1_code = data.get('m1Code')
        import1_base64 = data.get('import1')
        import2_base64 = data.get('import2')

        if not import1_base64 or not import2_base64:
            return func.HttpResponse("import1 または import2 が見つかりません。", status_code=400)

        # Base64デコードしてExcelファイルとして読み込み
        ex1_bytes = base64.b64decode(import1_base64)
        ex2_bytes = base64.b64decode(import2_base64)

        ex1_df = pd.read_excel(io.BytesIO(ex1_bytes), sheet_name='Sheet1', dtype=str, engine='openpyxl')
        ex2_df = pd.read_excel(io.BytesIO(ex2_bytes), sheet_name='Sheet1', header=[0, 1], engine='openpyxl')

        # 判定ロジック（簡略化例）
        m1_codes = ex1_df.iloc[8, 8:].dropna()
        m1_codes = m1_codes[~m1_codes.isin(['分類内(日本_PC／化粧品)', '分類内(花王G全て)', '全製品(花王G全て)', 'NaN'])]
        results = []
        for code in m1_codes:
            if code == m1_code:
                results.append((code, '同一'))
            else:
                results.append((code, '類似'))

        result_df = pd.DataFrame(results, columns=['M1コード', '判定結果'])

        def safe_format_m1(x):
            try:
                return f"{int(x):08d}"
            except (ValueError, TypeError):
                return str(x)

        result_df['M1コード'] = result_df['M1コード'].apply(safe_format_m1)
        ex2_df[('MI', 'Unnamed: 6_level_1')] = ex2_df[('MI', 'Unnamed: 6_level_1')].apply(safe_format_m1)

        def sampling(row):
            day1 = row.get(('Log Reduction', 'Day 1'))
            day3 = row.get(('Log Reduction', 'Day 3'))
            if pd.isna(day3) or day3 in ['N.A.', 'N.T.']:
                return '**'
            elif pd.isna(day1) or day1 in ['N.A.', 'N.T.']:
                return '*'
            return ''

        ex2_df['Sampling'] = ex2_df.apply(sampling, axis=1)

        ex2_df.columns = ['_'.join(col).strip() if isinstance(col, tuple) else col for col in ex2_df.columns]
        merged_df = pd.merge(ex2_df, result_df, left_on='MI_Unnamed: 6_level_1', right_on='M1コード', how='left')
        merged_df.drop(columns=['M1コード'], inplace=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            merged_df.to_excel(writer, index=False)

        result_base64 = base64.b64encode(output.getvalue()).decode('utf-8')

        request_no_col = [col for col in ex2_df.columns if 'Request No' in col]
        request_no = str(ex2_df[request_no_col[0]].iloc[0]) if request_no_col else "UNKNOWN"

        response_data = {
            "resultFile": result_base64,
            "requestNo": request_no
        }

        response_json = json.dumps(response_data)
        return func.HttpResponse(
            response_json,
            status_code=200,
            mimetype="application/json",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(response_json.encode('utf-8')))
            }
        )

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        print(f"Error: {str(e)}")  # ← 追加
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
