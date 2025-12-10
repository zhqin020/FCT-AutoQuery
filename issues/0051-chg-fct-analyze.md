```markdown
# Issue: 0051 - fct-analysis-change

**Summary**
1. 参数集中管理，主要参数和采集程序共用，兼容。包括输入文件路径（json文件），输出目录。 参数管理模块：src/lib/config.py
2. 数据源：优先选择数据库，数据库有关的参数在 src/lib/config.py 中配置
3. 如果 LLM 需要以文件方式输入，case 的 json 格式文件保存在 output 目录下，按年度存放在不同的目录， 年度信息也包含在case number 中，比如 IMM-1234-25, 是25年的case.
    -目录结构如下：
output
├── analysis
│   └── simple
│       ├── federal_cases_simple_details.csv
│       └── federal_cases_simple_summary.json
└── json
    ├── 2021
    │   ├── IMM-1000-21-20210101.json
    │   ├── IMM-10-21-20210101.json
    │   ├── IMM-1025-21-20210101.json
    │   ├── IMM-124-21-20210101.json
    │   ├── IMM-125-21-20210101.json
    │   ├── IMM-126-21-20210101.json
    │   ├── ......
    │   ├── IMM-98-25-20250101.json
    │   └── IMM-99-25-20250101.json
    ├── 2022
    │   ├── IMM-1000-22-20220101.json
    │   ├── IMM-126-22-20220101.json
    │   ├── ......
    │   ├── IMM-98-22-20220101.json
    │   └── IMM-99-22-20220101.json
    ├── 2023
    │   ├── IMM-1000-23-20230101.json
    │   ├── ......
    │   ├── IMM-1000-23-20230101.json
    │   ├── IMM-126-23-20230101.json
    │   └── IMM-99-23-20230101.json
    ├── 2024    

    - json 文件的格式：

{
  "case_id": "IMM-1-21",
  "case_number": "IMM-1-21",
  "title": "SANOD KUWAR v. MCI",
  "court": "Toronto",
  "date": "2021-01-03",
  "case_type": "Immigration Matters",
  "action_type": "Immigration Matters",
  "nature_of_proceeding": "Imm - Appl. for leave & jud. review - IRB - Refugee Appeal Division",
  "filing_date": "2021-01-03",
  "office": "Toronto",
  "style_of_cause": "SANOD KUWAR v. MCI",
  "language": "English",
  "url": "https://www.fct-cf.ca/en/court-files-and-decisions/court-files",
  "html_content": "",
  "scraped_at": "2025-12-06T18:52:19.796392",
  "docket_entries": [
    {
      "id": null,
      "case_id": "IMM-1-21",
      "doc_id": 1,
      "entry_date": "2021-06-04",
      "entry_office": "Ottawa",
      "summary": "Acknowledgment of Receipt received from Applicant, Respondent, Tribunal - sent by email with respect to Dismissed Certificate (ID 5) placed on file on 04-JUN-2021"
    },
    {
      "id": null,
      "case_id": "IMM-1-21",
      "doc_id": 2,
      "entry_date": "2021-06-04",
      "entry_office": "Ottawa",
      "summary": "(Final decision) Order rendered by Associate Chief Justice Gagné at Ottawa on 04-JUN-2021 dismissing the application for leave Decision endorsed on the record on the back of doc 1 received on 04-JUN-2021 Considered by the Court without personal appearance entered in J. & O. Book, volume 915 page(s) 156 - 156 Certificate of the order sent to all parties Transmittal Letters placed on file."
    },
    {
      "id": null,
      "case_id": "IMM-1-21",
      "doc_id": 3,
      "entry_date": "2021-04-01",
      "entry_office": "Ottawa",
      "summary": "Communication to the Court from the Registry dated 01-APR-2021 re: sent to Court for final disposition of leave application - no record filed"
    },
    {
      "id": null,
      "case_id": "IMM-1-21",
      "doc_id": 4,
      "entry_date": "2021-01-08",
      "entry_office": "Toronto",
      "summary": "Notice of appearance on behalf of the respondent filed on 08-JAN-2021 with proof of service on the applicant the tribunal"
    },
    {
      "id": null,
      "case_id": "IMM-1-21",
      "doc_id": 5,
      "entry_date": "2021-01-04",
      "entry_office": "Toronto",
      "summary": "Acknowledgment of Receipt received from Respondent with respect to doc. 1 placed on file on 04-JAN-2021"
    },
    {
      "id": null,
      "case_id": "IMM-1-21",
      "doc_id": 6,
      "entry_date": "2021-01-04",
      "entry_office": "Toronto",
      "summary": "Application for leave and judicial review against a decision IRB-RAD; decision dated 8-DEC-2020 and received 18-DEC-2020; TB9-34743 filed on 04-JAN-2021 Written reasons received by the Applicant Tariff fee of $50.00 received"
    }
  ]
}

4. 数据源采用哪种格式，可以在参数文件中设置

5. 目前程序的数据输入方式，和数据格式，如果和实际提供的有差距，需要进行修改。
