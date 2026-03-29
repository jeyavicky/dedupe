from flask import Flask, render_template, request, send_file, jsonify
import pandas as pd
import os
import io
import uuid

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Only CSV files are supported'}), 400

    try:
        df = pd.read_csv(file)
        total_rows = len(df)

        # Detect and exclude auto-increment ID columns before comparing duplicates.
        # A column is treated as an ID if its name matches common id patterns AND
        # its values are all unique integers (i.e. a serial key, not real data).
        def is_id_column(col):
            name_lower = col.strip().lower()
            id_patterns = ['id', '_id', 'id_', 'index', 'no', 'num', 'number', 'serial', 'row']
            name_match = any(name_lower == p or name_lower.endswith('_' + p) or name_lower.startswith(p + '_') for p in id_patterns) or name_lower in id_patterns
            if not name_match:
                return False
            # Also verify values are all unique (a true serial/auto-increment column)
            return df[col].nunique() == len(df)

        id_cols = [c for c in df.columns if is_id_column(c)]
        content_cols = [c for c in df.columns if c not in id_cols]

        if content_cols:
            # Drop duplicates based only on content columns (ignore ID cols)
            duplicate_mask = df.duplicated(subset=content_cols, keep='first')
            df_cleaned = df[~duplicate_mask].copy()
        else:
            # Fallback: use all columns
            df_cleaned = df.drop_duplicates()

        # Reset index so row numbers are clean in output
        df_cleaned = df_cleaned.reset_index(drop=True)

        cleaned_rows = len(df_cleaned)
        duplicates_removed = total_rows - cleaned_rows

        # Save cleaned file with a unique name
        filename = f"cleaned_{uuid.uuid4().hex[:8]}.csv"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        df_cleaned.to_csv(filepath, index=False)

        # Preview: first 10 rows — replace NaN with empty string for safe JSON
        preview_df = df_cleaned.head(10).fillna('')
        preview = preview_df.to_dict(orient='records')
        columns = list(df_cleaned.columns)

        return jsonify({
            'success': True,
            'total_rows': total_rows,
            'cleaned_rows': cleaned_rows,
            'duplicates_removed': duplicates_removed,
            'columns': columns,
            'preview': preview,
            'download_file': filename,
            'id_cols_ignored': id_cols   # tell frontend which cols were excluded
        })

    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/download/<filename>')
def download(filename):
    # Security: only allow files from uploads folder
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        filepath,
        mimetype='text/csv',
        as_attachment=True,
        download_name='cleaned_data.csv'
    )

if __name__ == '__main__':
    app.run(debug=True)