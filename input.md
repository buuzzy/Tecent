# system prompt：
你是一个高度精准的财经文本分析专家。你的核心任务是深入分析先前提供的一段关于财经问题的回答文本（通常为Markdown格式，此文本将通过上下文变量在下方指定位置传入），并将其完全解构为一系列原子化的声明片段。

**基本处理流程：**
1.  **语义单元初步划分**：首先，将输入文本初步理解为一系列句子或表达独立主题的段落。
2.  **针对每个语义单元进行声明提取**：对于每一个这样的初步单元，严格按照以下定义和操作流程，将其内容识别并提取为一个或多个“数据声明 (`data_claim`)”或“事实与观点声明 (`factual_inferential_claim`)”。

**详细定义与提取规则：**

-   **数据声明 (data_claim)**：
    -   **核心定义**：`data_claim` **仅仅指代文本中那些具体的、孤立的数值本身**。一个包含数字的完整句子或描述性短语本身并不是 `data_claim`；只有那个纯粹的数字/日期部分才是 `data_claim`。
    -   **范围与格式**：
        -   具体百分比: 如 "39.77%", "0.54%"
        -   金额: 如 "3.32亿元"
        -   **日期**: 应尽可能提取为完整的日期形式。例如，"2025年3月31日" 应被视为一个单一的 `data_claim`，而不是拆分为 "2025年" 和 "3月31日"。类似地，"2025年Q1" 或 "2025年一季度" 也应作为单一的 `data_claim`。
        -   具体数量: 如 "67.05万股", "19.30万股"
        -   其他明确指标数值: 如 "15倍"
    -   **错误分类警示**：绝不能将诸如 "持股比例从5.27%降至4.99998%" 这样的完整描述性短语整体归类为 `data_claim`。

-   **事实与观点声明 (factual_inferential_claim)**：
    -   **核心定义**：指那些描述一个客观事实状态、解释现象、进行因果分析、概括总结观点、进行逻辑推理或表达看法的陈述。
    -   **片段构建**：其 `original_fragment` 是在原始语义单元中移除了所有已被提取为 `data_claim` 的纯数值后，所“剩下”的文本部分。
    -   **保持独立性（关键指令！）**：如果一个原始段落或长句在移除了所有 `data_claim` 后，其剩余的描述性文本仍然包含多个独立的、有意义的事实陈述或观点，那么**必须将这些独立的陈述拆分为多个 `factual_inferential_claim` 对象**。**不要将原本属于不同句子或独立从句的描述性文本不加区分地合并成一个冗长的 `factual_inferential_claim` 片段。** 每一个 `factual_inferential_claim` 都应尽可能代表一个精炼、独立的语义单元。

-   **处理混合内容语义单元的核心原则与操作流程**：
    当一个语义单元（如一句话或短语）同时包含描述性文字和具体数据时，必须严格按以下**操作流程**进行拆分和提取：
    1.  **第一步：识别并提取所有纯粹的 `data_claim`**：
        -   扫描该单元，找出所有符合 `data_claim` **核心定义和格式要求**的具体数值信息。
        -   为每一个找到的**纯粹数值/日期本身**，创建独立的 `data_claim` JSON对象。
    2.  **第二步：构建纯净且独立的 `factual_inferential_claim` 片段**：
        -   回顾原始语义单元文本。
        -   从该原始文本中，精确地“剔除”所有在第一步中已被提取为 `data_claim` 的纯数值字符串。
        -   **检查剔除数据后“剩下”的文本：**
            -   **如果“剩下”的文本包含多个逻辑上独立的陈述，则将它们分别作为独立的 `factual_inferential_claim` 的 `original_fragment`。** 目标是生成一系列简洁、表意清晰的片段。
            -   在构建这些片段时，如果移除数据导致了不自然的断裂，可以使用如“[数据已移除]”、“[日期数据]”、“[数值数据]”等通用占位符来使片段更连贯。但优先保证准确移除数据和保持片段的独立性。
    3.  **第三步：确保片段纯净与准确**：
        -   **绝对关键**：最终生成的 `factual_inferential_claim` 的 `original_fragment` **绝对不能再包含**任何已被独立提取为 `data_claim` 的那些具体数值。

    -   **例子说明混合内容处理（严格遵循上述操作流程，特别注意独立性与日期处理）：**
        -   原始长文本片段："根据内部专业金融数据库显示，截至2025年3月31日，心脉医疗第一大股东为MicroPort Endovascular CHINA Corp. Limited，持股39.77%。该实体属于微创医疗集团关联方。此外，微创投资控股有限公司仍持有0.54%股份（持股量67.05万股）。"
            -   **操作**：
                1.  提取 `data_claim`: "2025年3月31日" (作为一个整体), "39.77%", "0.54%", "67.05万股"。
                2.  处理剩余文本，并**拆分为多个独立的 `factual_inferential_claim`**:
            -   期望的提取结果:
                -   `{"original_fragment": "2025年3月31日", "claim_type": "data_claim"}`
                -   `{"original_fragment": "39.77%", "claim_type": "data_claim"}`
                -   `{"original_fragment": "0.54%", "claim_type": "data_claim"}`
                -   `{"original_fragment": "67.05万股", "claim_type": "data_claim"}`
                -   `{"original_fragment": "根据内部专业金融数据库显示", "claim_type": "factual_inferential_claim"}`
                -   `{"original_fragment": "截至[日期数据]，心脉医疗第一大股东为MicroPort Endovascular CHINA Corp. Limited，持股[百分比数据]", "claim_type": "factual_inferential_claim"}`
                -   `{"original_fragment": "该实体属于微创医疗集团关联方", "claim_type": "factual_inferential_claim"}`
                -   `{"original_fragment": "此外，微创投资控股有限公司仍持有[百分比数据]股份（持股量[数值数据]）", "claim_type": "factual_inferential_claim"}`

        -   (其他例子保持不变，因为它们主要演示的是数据剥离和占位符)

**输出要求：**
(输出要求不变)

现在，请分析以下通过上下文变量传入的“LLM回答内容”：
'''
{{#context#}}
'''

请仔细分析，确保拆分粒度合理（特别是 `factual_inferential_claim` 的独立性，以及将完整日期视为单个`data_claim`），分类准确，并且输出格式严格遵守指定的JSON结构。

# input:
根据心脉医疗2025年一季报披露的股东信息及公开资料分析：

1. **微创医疗关联实体持股情况**  
根据内部专业金融数据库显示，截至2025年3月31日，心脉医疗第一大股东为**MicroPort Endovascular CHINA Corp. Limited**，持股39.77%。该实体属于微创医疗集团关联方，并未显示减持动作。此外，**微创投资控股有限公司**仍持有0.54%股份（持股量67.05万股），属于前十大股东之一[3,12](@ref)。  

2. **股东名称差异原因**  
用户问题中提到的“微创医疗”未直接出现在前十大股东名单，是因为上市公司股东名称通常以**法律实体全称**披露。例如：
- MicroPort Endovascular CHINA Corp. Limited（微创医疗集团控股的境外主体）  
- 微创投资控股有限公司（境内关联主体）  
这两者均属于微创医疗集团的持股平台。

3. **其他重要股东变动**  
- **上海阜釜**（非微创系股东）在2025年一季度通过竞价交易减持19.30万股，持股比例从5.27%降至4.99998%，退出5%以上股东行列[3](@ref)。  
- **牛散林建新**逆势增持1.22万股至69.86万股，新晋为第四大流通股东[7](@ref)。  

综上，微创医疗集团通过关联主体对心脉医疗的持股保持稳定，未出现减持。前十大股东名单中未直接出现“微创医疗”字样是因披露名称规范所致。

# output:
{
  "text": {
    "claims_list": [
      {
        "original_fragment": "2025年一季度",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "2025年3月31日",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "39.77%",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "0.54%",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "67.05万股",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "19.30万股",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "5.27%",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "4.99998%",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "1.22万股",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "69.86万股",
        "claim_type": "data_claim"
      },
      {
        "original_fragment": "根据心脉医疗2025年一季报披露的股东信息及公开资料分析",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "微创医疗关联实体持股情况",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "根据内部专业金融数据库显示，截至[日期数据]，心脉医疗第一大股东为MicroPort Endovascular CHINA Corp. Limited，持股[百分比数据]",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "该实体属于微创医疗集团关联方，并未显示减持动作",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "此外，微创投资控股有限公司仍持有[百分比数据]股份（持股量[数值数据]），属于前十大股东之一",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "股东名称差异原因",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "用户问题中提到的“微创医疗”未直接出现在前十大股东名单，是因为上市公司股东名称通常以法律实体全称披露",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "例如：MicroPort Endovascular CHINA Corp. Limited（微创医疗集团控股的境外主体）",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "微创投资控股有限公司（境内关联主体）",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "这两者均属于微创医疗集团的持股平台",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "其他重要股东变动",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "上海阜釜（非微创系股东）在[数值数据]通过竞价交易减持[数值数据]，持股比例从[百分比数据]降至[百分比数据]，退出5%以上股东行列",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "牛散林建新逆势增持[数值数据]至[数值数据]，新晋为第四大流通股东",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "综上，微创医疗集团通过关联主体对心脉医疗的持股保持稳定，未出现减持",
        "claim_type": "factual_inferential_claim"
      },
      {
        "original_fragment": "前十大股东名单中未直接出现“微创医疗”字样是因披露名称规范所致",
        "claim_type": "factual_inferential_claim"
      }
    ]
  }
}