# 学生生活知识核验与检索改进（2026-11-17）

本记录针对独立 student-v4-20261117 快照；不表示运行中的数据库或 Dify 已自动更新。

## 内容与数据路径

保留德国、新加坡两个外部知识库标识。它们检索同一数据库 overseas_life_knowledge 的已发布内容，不是两个仅存放链接的静态库。目录 JSON 为审核/导入资料，网站指南和助手运行时均从数据库读取。继续保持 12 篇指南、双国各六类，各指南六条，共 72 条问答。重要事实、联系号码、适用条件及操作步骤写入 FAQ 正文；详情链接为辅助。

本轮增加就医预约与准备、夜间医疗、交通支付与实际乘坐、票制范围、租房核验、入境清单和学习资源。新加坡公交步骤与 MRT 步骤分别处理；无需注册 SimplyGo 的说明并入支付问答。

## 答复规则

- 本轮原问中明确国家优先；否则使用学生已登记国家。历史上随口问过另一国，不永久覆盖个人资料。当前明确所在国家或主动选国可以覆盖默认。两国比较需明确本轮查哪国。登记去向不是实时定位。
- 原问的实际需求决定类别与细分主题。Dify扩写的检索词和错误证据编号不能把普通就医问题变成保险问题。
- 一次明确询问多个相关方面时合并最多三个审核条目，正文逐条取自审核内容，附对应来源。其他相关问题作为可选继续提问。
- 德国交通先提供通用操作，再补充城市及起终点以确认票制；新加坡路线只需补起终点，不无故再问国家或城市。
- 无对应审核知识时明确没有可靠答案，不猜学校、个人截止、价格、地址、报销或预约结果。SGH、NUS及柏林示例保留适用范围。

## 核验方法与来源

核验日期为 2026-11-17。采用机构官方网页，以短事实重新表述；没有整页复制，也没有保存长段原文。以下表格只列本次使用的事实边界；联系方式、政策及服务仍需定期复核。就医内容限服务渠道与办理流程，不给出诊断。

| 官方来源 | 本次纳入及适用边界 |
| --- | --- |
| [Make it in Germany · 住房与登记](https://www.make-it-in-germany.com/en/arriving-living/getting-started/housing-registration) | 搬入后登记、有效证件及房东入住确认；冷租与暖租按合同区分。城市材料以当地机关为准。 |
| [Make it in Germany · 留学到达与注册准备](https://www.make-it-in-germany.com/en/study-vocational-training/studying-in-germany/planning) | 安排注册、住宿和保险，并向本人院校核对到校手续。 |
| [DAAD · 入学条件与注册](https://www.daad.de/en/studying-in-germany/requirements/overview/) | 录取与入学注册分开，注册方式、要求和日期向International Office核对。未猜测个人截止。 |
| [DAAD · 医疗与保险](https://www.daad.de/en/studying-in-germany/living-in-germany/health-insurance/) | 预约时说明保险类型，全科医生可建议专科；不承诺免费或报销。 |
| [116117 · 英文就医说明](https://www.116117.de/de/englisch.php) | 诊所关闭且当天需要非危及生命帮助可用116117，电话仅德语；网站查诊所；紧急情况112。 |
| [Make it in Germany · 交通出行](https://www.make-it-in-germany.com/en/arriving-living/getting-started/driving-licence-mobility) | 公共交通票制依地区和线路；核对当地交通协会路线、票价及有效范围。未收录票价。 |
| [Deutsche Bahn · Deutschlandticket适用交通](https://www.bahn.de/faq/deutschlandticket-verkehrsmittel-deutschland) | Deutschlandticket适用于参与范围的当地/区域交通；不普遍适用ICE、IC、EC，特殊线路另核对。 |
| [Berlin.de · 柏林票制与路线](https://www.berlin.de/en/public-transportation/1772016-2913840-tickets-fares-and-route-maps.en.html) | 柏林纸票验证要求，仅作为柏林例子，不泛化到全国或所有票种。另以BVG旅游FAQ交叉核对激活说明。 |
| [DAAD · 学生租房](https://www.daad.de/en/studying-in-germany/living-in-germany/renting/) | 宿舍、合租、独立或临时住房；防范不合理低价、境外房东及预付催促。未承诺房源。 |
| [Make it in Germany · 日常与紧急求助](https://www.make-it-in-germany.com/en/arriving-living/getting-started/everyday-knowledge) | 110警方、112消防与急救，说明实际位置及事件。 |
| [ICA · SG Arrival Card](https://www.ica.gov.sg/information-and-e-services/entry-and-departure/entering-singapore/sg-arrival-card-with-electronic-health-declaration) | 适用旅客抵达前三天内（含当天）提交；官方免费；有陆路居民及不入境转机等例外；不替代签证和护照。 |
| [ICA · 学生准证](https://www.ica.gov.sg/information-and-e-services/long-term-visit-and-study/student-s-pass) | 学校类别与全日制课程决定适用学生准证流程；其他有效准证及豁免按个人类别核对。 |
| [ICA · 入境要求](https://www.ica.gov.sg/enter-transit-depart/entering-singapore) | 非新加坡护照通常至少六个月有效期；本人签证及准证条件按ICA核对。 |
| [MOH · 获取医疗帮助](https://www.moh.gov.sg/seeking-healthcare/getting-medical-help/) | GP/综合诊疗所与急诊用途不同；一般就医入口及开放时间查询，不做个人诊断。 |
| [SCDF · 紧急医疗服务](https://www.scdf.gov.sg/home/about-scdf/emergency-medical-services) | 紧急医疗995，描述地点/邮编或地标、事件和回拨方式，听从接线员。未把即将停用的1777纳入通用答复。 |
| [MOH · 看医生](https://www.moh.gov.sg/seeking-healthcare/getting-medical-help/seeking-a-doctor/) | 一般医疗可先了解GP等基层渠道；后续转诊由医疗专业人员决定。 |
| [SGH · 门诊就诊准备](https://www.sgh.com.sg/clinic-visit/planning-for-your-visit) | SGH首次门诊示例包含身份证件、转诊信及已有记录，明确不是全部医院/诊所统一清单。 |
| [SimplyGo · 非接触银行卡使用说明](https://www.simplygo.com.sg/faqs/cards-and-charms/simplygo/contactless-bank-cards) | 支持的非接触支付、无需先注册、同卡同设备、境外卡附加费核对及行程查询。未编造金额。 |
| [LTA · 使用同一设备进出站](https://www.lta.gov.sg/content/ltagov/en/newsroom/2024/2/media-replies/use-the-same-device-or-card-to-tap-in-and-out-on-public-transpor.html) | 实体卡与绑定手机/手表混用可能造成不匹配；固定同一卡片和设备进出。 |
| [LTA · 公共交通与行程规划](https://www.lta.gov.sg/content/ltagov/en/getting_around/public_transport/plan_your_journey.html) | LTA/MyTransport路线、方向、换乘、出口；支付工具、成人票与优惠资格；公交现金与轨道交通不能混淆。 |
| [Go-Ahead Singapore · 乘车常见问题](https://go-aheadsingapore.com/faqs/) | 运营商指引核对线路、提前示意上车、成功感应和到站前按铃；结合LTA同卡规则整理公交步骤。 |
| [NUS OSA · 本校住宿选择](https://osa.nus.edu.sg/accommodation/hostel-options/) | NUS住宿选择和申请只适用于该校相应对象，不推断其他学校资格或空位。 |
| [SPF · 防范冒充房产中介的租房诈骗](https://www.police.gov.sg/Media-Hub/News/2024/20241121_police_advisory_on_rental_scams_involving_the_impersonation_of_property_agents) | 冒用真实中介图片、视频或注册资料催促看房前付款，需独立核验并安排真实看房。 |
| [CEA · 核实房产中介](https://www.cea.gov.sg/consumers/engaging-a-property-agent/check-if-your-property-agent-is-registered/) | 按对方实际联络电话号码查询Public Register，姓名或编号本身不足以确认联络人身份。 |
| [NLB · 图书馆位置与开放时间](https://www.nlb.gov.sg/main/visit-us/our-libraries-and-locations) | 按分馆核对地址、开放时间与设施，未生成未经查询的附近地点。 |
| [NLB · 会员类别](https://www.nlb.gov.sg/main/services/library-membership/types-of-membership) | 会员按身份分类，外国居民与公民/永久居民方案不同；进入空间不等于免费借书。 |
| [NUS Computing · Information for Freshmen](https://www.comp.nus.edu.sg/freshmen/) | Academic Advisory Service仅作NUS计算机学院支持渠道例子，其他院校使用本校官方安排。 |
| [新加坡政府产品报告 · 图书馆座位预约](https://reports.open.gov.sg/sbs) | 政府产品目录确认NLB座位预约服务存在；空位、日期、资格与到场规则到实际预约页面核对。 |
| [SPF · 联系方式](https://www.police.gov.sg/Contact-Us) | 警方即时求助999，不安全通话时70999短信；犯罪线索1800 255 0000与紧急求助分开。 |

交叉核对：[BVG旅游票说明](https://www.bvg.de/en/tourists/tickets)支持柏林纸票验证及数字票激活规则，明确已激活票/订阅存在差异；未外推为德国统一制度。

## 来源迁移

仅为两篇已存在指南声明精确的旧主来源：德国学习旧 DAAD ankommen 页面已不可用，改为 DAAD 入学条件页面；德国交通旧 mobility-germany/print 页面换成当前官方 mobility 页面。目录使用 previous_source_url，导入器只允许匹配声明旧值的受控迁移，其他未知来源冲突应继续拒绝。FAQ保留各自直接来源。

## 验证

执行 tests/modules/test_student_experience.py 与 tests/modules/test_student_knowledge_practical.py：113 项通过。包括72条审核问题逐条检索，双国号码隔离、未知问题拒绝、国家默认/临时选择、医院不被保险词劫持、MRT准备及乘坐、同设备进出、公交上下车、德国票适用范围、SGH示例范围以及多相关问题合并。测试使用隔离 SQLite，不冒充真实 Dify 或线上验收。
