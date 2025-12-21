from lib.config import Config
from sqlalchemy import create_engine, text
import pandas as pd
import json

db_cfg = Config.get_db_config()
DB_CONNECTION_STR = f"postgresql://{db_cfg.get('user')}:{db_cfg.get('password')}@{db_cfg.get('host')}:{db_cfg.get('port')}/{db_cfg.get('database')}"
engine = create_engine(DB_CONNECTION_STR)

case_id = 'IMM-6260-25'

with engine.connect() as conn:
    # Get analysis result
    analysis_df = pd.read_sql(text(f"SELECT * FROM case_analysis WHERE case_number = '{case_id}'"), conn)
    # Get docket entries
    docket_df = pd.read_sql(text(f"SELECT * FROM docket_entries WHERE case_number = '{case_id}' ORDER BY date_filed ASC"), conn)

result = {
    "analysis": analysis_df.to_dict('records'),
    "docket": docket_df.to_dict('records')
}

print(json.dumps(result, indent=2, default=str))
