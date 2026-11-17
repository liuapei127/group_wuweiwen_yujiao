-- Apply after 024. Update only the unchanged, published default card.
UPDATE website_section_card AS card
JOIN website_section AS section ON section.id = card.section_id
SET card.content = CONCAT_WS(CHAR(10),
    card.content,
    '',
    '初中毕业生可了解以下路径：',
    '• 2+2 新加坡定向培养本科班：先在国内学习两年，再衔接新加坡阶段的学习。',
    '• 2+2+1 本硕连读：完成上述本科阶段后，可继续了解硕士申请。',
    '',
    '大专毕业生可了解以下路径：',
    '• 专升本：可了解专科毕业后衔接本科的升学方向。',
    '',
    '以上为项目资料中的升学路径介绍。具体院校、学制、招生批次和申请条件，请以当期公告或顾问核对为准。')
WHERE section.anchor = 'programs'
  AND section.published = 1
  AND card.published = 1
  AND card.title = '新加坡国际本硕升学计划'
  AND BINARY card.content = CONCAT_WS(CHAR(10),
    '提供面向不同学历阶段的升学路径，以及酒店和航空方向的就业项目。',
    '',
    '高中毕业生可了解以下两条升学路径：',
    '• 0.5/1+2 新加坡定向培养本科班：先在国内读半年或一年预科，再赴新加坡学习约两年，按项目安排完成本科阶段。',
    '• 0.5/1+2+1 本硕连读：完成上述本科阶段后，可继续申请约一年的硕士课程。',
    '应往届高中毕业生属于项目列明的招生对象。具体院校、开班时间和入学考核以当期招生安排为准，录取以审核结果为准。');
