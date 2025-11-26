

# 重大问题修改

**项目名称**：联邦法院案件自动查询系统 (FCT-AutoQuery)
**版本号**：V1.1
**日期**：2025-11-25 

## 1. 问题

### 1.1 必须输入JSON 文件
目前的版本出现了错误，只记录数据库，没有保存json 文件
文件按年划分目录
文件名 <case number>-<updatedate>.json, 例如：
IMM-1-25-20251125.json
---

### 1.2 批量采集时，效率需要优化
目前，在每个case 采集时，都要重新初始化浏览器，这个在实际操作中是不合理的。
在采集一条记录完成后，关闭 dialog box, 可以继续下一条数据的采集：
清空上一条记录的 case number, 重新输入新的 case number, 点击 'submit'， 进行当前记录的显示和采集。 然后重复前面的操作，进行后续记录的处理
---


## 2. 附联邦法院网站查询功能，人工操作流程（多条记录）

1. 进入 页面： https://www.fct-cf.ca/en/court-files-and-decisions/court-files
2.  点击 'Search by court number' Tab,  切换到查询Form
3. 在Court 下拉框中，选择 'Federal Court',  其余两项是'Federal Court of Apeal', 'Both'
4. 在 'Search by court number:' 输入框中，输入编号，比如 IMM-23456-25'
5. 点击 'Submit'
6.  下面会显示一个表格，如果没有结果，表格中显示 'No data available in table'
7.  如果有记录，将显示查找结果，columns: 'Court Number', 'Style of Cause', 'Nature of Processing', 'Parties', 'More'
8. 点击 'Parties' cell，会弹出一个对话框，显示案件双方的信息
9. 点击 'More' cell, 会弹出详情对话框，我们需要采集的数据全部在这个页面中
10. 点击 'Close' 关闭对话框，回到 search page, 'Search by court number' Tab 仍然保持选中状态
11. 清除上一条记录的case number, 输入下一个编号，继续查询
