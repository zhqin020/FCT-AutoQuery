# filing_date IS NULL 记录分析报告

## 概述

本报告分析了数据库中所有 `filing_date IS NULL AND status='success'` 的记录，总计 **969 条记录**。

## 数据导出

### 完整数据
- **文件**: `output/null_filing_date_cases.json`
- **大小**: 0.99 MB
- **记录数**: 969 条
- **包含**: 完整的 case 信息和最后一个 docket_entries 记录

### 样本数据
- **文件**: `output/null_filing_date_sample.json` 
- **大小**: 17.50 KB
- **记录数**: 20 条样本
- **用途**: 快速检查数据结构

## 关键发现

### 1. 年份分布
- **2021年**: 873 条记录 (90.1%)
- **2022年**: 96 条记录 (9.9%)

### 2. 数据完整性
- **所有记录都有 docket_entries**: 969 条 (100%)
- **缺失 case_type**: 565 条 (58.3%)
- **缺失 office**: 952 条 (98.2%)
- **缺失 style_of_cause**: 0 条
- **缺失 nature_of_proceeding**: 0 条

### 3. 案件类型分布
- **Immigration Matters**: 404 条 (41.7%)
- **Unknown/未指定**: 565 条 (58.3%)

### 4. 案件性质 (前5)
1. Arising outside Canada: 330 条 (34.1%)
2. Other Arising in Canada: 294 条 (30.3%)
3. IRB - Refugee Appeal Division: 246 条 (25.4%)
4. IRB - Refugee Protection Division: 50 条 (5.2%)
5. Pre-removal risk assessment: 26 条 (2.7%)

### 5. 抓取时间范围
- **最早**: 2025-12-04
- **最晚**: 2025-12-10
- **高峰**: 2025-12-08 (493 条记录)

### 6. Docket 日期分布 (前10)
1. 2022-04-01: 19 条记录
2. 2021-07-19: 10 条记录
3. 2022-05-27: 9 条记录
4. 2021-12-15: 8 条记录
5. 2022-03-01: 7 条记录

## 数据质量问题

### 1. Case年份 vs Docket年份不匹配
- **问题**: 86 条案例 (8.9%) 的 case_number 年份与 docket 年份差异超过1年
- **示例**: IMM-1175-21 (2021年) 的 docket 日期为 2024-02-29
- **建议**: 需要验证这些案例的年份准确性

### 2. 重复的 style_of_cause
- **问题**: 发现 8 组重复的当事人信息
- **最严重**: "Edgewater Plants Inc. v. The Minister of Employment and Social Development..." 重复 3 次
- **建议**: 检查是否为真正的重复案例或数据录入错误

### 3. 缺失关键字段
- **Office 字段**: 98.2% 的案例缺失办公室信息
- **Case Type 字段**: 58.3% 的案例缺失类型信息
- **建议**: 可能需要从其他数据源补充这些信息

## 修复建议

### 1. 自动修复 filing_date
可以使用最早的 docket 日期作为 filing_date：

```sql
UPDATE cases c
SET filing_date = (
    SELECT MIN(date_filed)
    FROM docket_entries de
    WHERE de.case_number = c.case_number
)
WHERE c.filing_date IS NULL
  AND c.status = 'success'
  AND EXISTS (
      SELECT 1 FROM docket_entries de2
      WHERE de2.case_number = c.case_number
  );
```

### 2. 验证数据一致性
- 检查 case_number 年份与实际活动时间的一致性
- 验证重复案例是否需要合并或标记
- 补充缺失的 office 和 case_type 信息

### 3. 质量控制流程
- 建立数据抓取时的 filing_date 验证机制
- 添加 case_number 年份与 docket 日期的一致性检查
- 定期检查重复记录

## 示例案例分析

### 案例 1: IMM-1001-21
- **当事人**: Bushra Adnan Khan et Al. v. MCI
- **Case年份**: 2021
- **Docket日期**: 2022-03-01 (Ottawa)
- **摘要**: Acknowledgment of Receipt received from Applicant Respondent Tribunal
- **问题**: Docket 日期晚于 case 年份超过1年

### 案例 2: IMM-1003-21  
- **当事人**: Farshad Zare Dastenaei v. MINISTER OF CITIZENSHIP AND IMMIGRATION
- **Case年份**: 2021
- **Docket日期**: 2021-03-22 (Vancouver)
- **摘要**: Notice of discontinuance on behalf of applicant
- **状态**: 时间跨度合理

## 结论

1. **总体数据质量良好**: 所有记录都有完整的 docket_entries 信息
2. **主要问题集中在 filing_date**: 可以通过 docket 日期自动修复
3. **需要人工审核的案例**: 86 条年份不匹配的案例需要进一步验证
4. **建议优先处理**: 使用 SQL 语句批量修复 filing_date，然后人工审核异常案例

## 相关文件

1. `export_null_filing_date_cases.py` - 数据导出脚本
2. `analyze_null_filing_date_cases.py` - 基础分析脚本  
3. `detailed_case_analysis.py` - 详细分析脚本
4. `export_sample_null_cases.py` - 样本导出脚本
5. `output/null_filing_date_cases.json` - 完整数据
6. `output/null_filing_date_sample.json` - 样本数据