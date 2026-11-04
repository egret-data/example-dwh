# Digest: Alibaba Cloud MaxCompute "Build and optimize a data warehouse"

Method note: WebFetch returned only page shells (the site renders client-side) and refused verbatim output.
All content below was read from the site's own page-content JSON endpoint
(`https://www.alibabacloud.com/help/json/document_detail.json?alias=/maxcompute/user-guide/<slug>&website=intl&language=en`),
i.e. the raw published HTML of each page, converted to text. Quotes are verbatim from that text. Page "last updated" per site: Sep 11, 2026.
Base URL for all pages: `https://www.alibabacloud.com/help/en/maxcompute/user-guide/<slug>`.

## Page inventory (19 found, 16 with body text, 3 empty container nodes)

| # | Title | Slug | Status |
|---|-------|------|--------|
| 1 | Build and optimize a data warehouse (section index) | build-and-optimize-a-data-warehouse | read; EMPTY container, no body |
| 2 | Data warehouse build process | overall-process | read |
| 3 | Define requirements | determine-business-requirements | read |
| 4 | Analyze a business process | analyze-business-processes | read |
| 5 | Partitioning data domains | divide-data-domains | read |
| 6 | Define dimensions and build a bus matrix | define-dimensions-and-build-a-bus-matrix | read |
| 7 | Define statistical metrics | specify-statistical-metrics | read |
| 8 | Architecture and model design | architecture-and-model-design | read; EMPTY container (redirects to #9) |
| 9 | Select a technical architecture | select-a-technical-architecture | read |
| 10 | Data warehouse layers | divide-a-data-warehouse-into-layers | read |
| 11 | Data access rules between warehouse layers | specify-the-principles-for-using-data-at-different-layers | read |
| 12 | Design a data model | design-a-data-model | read; EMPTY container (children: DIM, DWD, DWS) |
| 13 | Conformed dimension layer (DIM) | dim-layer | read |
| 14 | Data Warehouse Detail (DWD) layer | data-warehouse-detail-layer | read |
| 15 | Common summary fact layer (DWS) | data-warehouse-service-layer | read |
| 16 | Project assignment and security | project-allocation-and-security | read |
| 17 | Establish a performance baseline | performance-benchmark-establishment | read |
| 18 | Data warehouse performance optimization | data-warehouse-performance-optimization | read |
| 19 | Result validation | result-verification | read |

Discovery: sub-pages were found by scanning site node IDs near the section (114420-114700, 118560-118720) plus search hits for slugs. The sidebar tree itself is not served as text, so a sibling page with a far-away node ID could in principle be missed. There is NO ADS-layer page, NO ODS-layer page and NO separate naming-conventions page in this section; ODS/ADS are described only on #10, #11, #16.
Images/diagrams (process figure, term-relationship figures, layer figure, project figure) are not readable as text; marked "[figure not read]".

---
## 2. Data warehouse build process  (overall-process)
Content: a process figure [figure not read] and a glossary ("Terms"). Verbatim:
- "Business segment: A method for dividing a business at a higher level than a data domain. This method is suitable for large business systems."
- "Dimension: A concept from the Dimensional Modeling methodology proposed by Ralph Kimball. ... A dimension is a collection of properties and can also be called an entity object."
- "Property (dimension property): A column within a dimension. Dimension properties are used for query constraints, grouping, and report labels."
- "Measure: In Dimensional Modeling, a measure is also known as a fact ... A measure is usually numerical data and acts as a fact in a logical fact table."
- "Metric: Metrics are divided into atomic metrics and derived metrics. An atomic metric is a measure of a business event or behavior. It is the most basic, indivisible metric in a business definition. It is a noun with a clear business meaning ..., such as payment amount."
- "Atomic metric = Business process + Measure."
- "Derived metric = Period + Modifier + Atomic metric. A derived metric defines the business statistical scope for an atomic metric."
- "Business filter: Defines the business scope for statistics. It filters records that match business rules. This is similar to the condition in a where clause in SQL, but does not include a time range."
- "Statistical period: The time range used for statistics, such as the last day or the last 30 days."
- "Statistical granularity: ... similar to the group by clause in an SQL aggregation operation. Granularity is a combination of dimensions that specifies the statistical scope. For example, if a metric measures a seller's transaction volume in a specific province, the granularity is the combination of the seller and region dimensions. If you count data for an entire table, the granularity is the entire table. ... Statistical granularity is often used as a modifier for a derived metric."

## 3. Define requirements  (determine-business-requirements)
- Business investigation via "surveys and interviews": org structure/responsibilities of users; "The overall business architecture, the connections between business segments, and the information flow"; "The main features of and data collected by each existing business segment."
- Example: Company A e-commerce, four modules: "investment, supply chain, marketing, and service". Table of "data feature modules" (Product Management, User Management, Purchase Flow, Transaction Orders, User Feedback) with Y/N inclusion per segment. Focus: "Transaction Orders data feature module of the marketing business segment".
- Example requirements: total sales of a category (kitchenware) by province for previous day; top 10 products by sales; purchasing power (average spend per person) by province.
- Requirements analysis: "Gather requirements by communicating with analysts and business operations staff" or "Analyze existing reports in the reporting system." "you must identify the metrics from business analyses or reports, along with their definitions and granularity. Granularity can be used as an input for dimensions."
- Questions to answer: what dimensions/granularity/measures; how to design DWD, DWS and common dimension layer and whether common metrics exist; "Does data need to be made redundant or stored in the data warehouse summary layer?"
- "The output of a requirements analysis is typically a document that records atomic and derived metrics."

## 4. Analyze a business process  (analyze-business-processes)
- "A business process is a series of distinct events." Analysis lists each stage with technology/data/system details; questions: "What data does each business process generate and which database stores it?", "What data does each stage ... produce and what does that data contain?", "When is the data updated and what is the logic behind the updates?"
- "A business process can be a single event, such as a payment or refund. It can also be the state of an event, such as a current account balance. Or, it can be a workflow that consists of a series of related events."
- "you must determine the required level of detail and scope to choose the correct granularity. After you identify the dimension tables and choose the granularity, you can design the dimension tables."
- Example flow: Create Order, Buyer Pays, Seller Ships, Confirm Receipt; focus on Confirm Receipt (= successful transaction).

## 5. Partitioning data domains  (divide-data-domains)
- "A data domain is a collection of related data subjects. It classifies business objects at a high level". "A data domain is a collection of abstract business processes or dimensions used for business analysis."
- "ensure that they cover all current business needs. The structure must also be flexible. New business activities should fit into existing domains or be used to create new ones." Partition "after you complete your business research".
- "You can partition data domains by department, business process, or functional module."
- Example table (domain -> processes): Member and store domain: Registration, logon, decoration, store opening, store closing | Product domain: Publishing, listing, delisting, relisting | Log domain: Impressions, views, clicks | Transaction domain: Placing orders, payment, shipping, confirming receipt | Service domain: Adding products to favorites, visits, training, coupon collection | Procurement domain: Product procurement, supply chain management.

## 6. Define dimensions and build a bus matrix  (define-dimensions-and-build-a-bus-matrix)
- Dimensions defined by analysing business processes; confirm-receipt process depends on "product and delivery location". Product dimension attributes: Product ID (primary key), name, transaction price, condition ("1 for New, 2 for Unused, 3 for Used" here; the DIM page says 0/1/2: source inconsistency), category ID/name, commodity ID/name (listed as Category ID/name), buyer ID, status ("0 Normal, 1 Deleted, 2 Delisted, 3 Never listed"), city, province. Region dimension: city code/name, province code/name.
- Rule: "A core principle of dimensional modeling is to ensure that each dimension is unique within the enterprise data warehouse. For example, Company A can have only one definition for the product dimension. The province code dimension ... must convey the same information across all business processes."
- Bus matrix: "The matrix maps business processes to their related dimensions." Rows = Data Domain/Process (Transaction: Place Order, Payment, Shipment, Confirm Receipt); columns = "Conformed Dimensions" (Purchase Province, Purchase City, Category ID, Category Name, Brand ID, Brand Name, Product ID, Product Name, Transaction Amount); cells Y/N ("Y indicates that the dimension is included. N indicates that it is not included."). Place Order/Payment/Shipment: Y for all but Transaction Amount = N; Confirm Receipt: all Y. (Source oddity: a measure, Transaction Amount, appears as a matrix column.)

## 7. Define statistical metrics  (specify-statistical-metrics)
- "An atomic metric defines a clear statistical scope and calculation logic: Atomic Metric = Business Process + Measure. A derived metric is a common statistical metric: Derived Metric = Period + Modifier + Atomic Metric."
- "You can create atomic metrics only after the business process is defined. You can create derived metrics after you understand the specific report requirements. You must create an atomic metric before you create a derived metric."
- "Atomic metrics, modifier types, and modifiers belong to a business process. A modifier inherits the data domain from its modifier type."
- "A derived metric can have multiple modifiers, depending on its specific semantics." Example: "payment amount for product A in the last month ... The period is last month, the modifier is product A, and the atomic metric is payment amount."
- "A derived metric belongs to only one atomic metric. It inherits the data domain from the atomic metric, not from the modifier."
- Tutorial: business process = confirm receipt; measure = product sales amount; atomic metric "successful product transaction amount". Derived: "Total sales of each kitchenware product by province for the last day"; "Per capita spending on kitchenware products by province for the last day (total spending divided by the number of users)". Top-10 = sort derived metric descending.
- No "calculated/composite metric" type is defined on this page.

## 8/9. Architecture and model design / Select a technical architecture  (select-a-technical-architecture)
- Container page has no body. #9: MaxCompute = "offline compute engine"; DataWorks = Data Integration, Data Development, Data Quality, data security, Data Management. Data flow: Ingestion (Data Integration pulls raw data into MaxCompute) -> Processing (Data Development) -> Serving (analytics, reporting, downstream apps).

## 10. Data warehouse layers  (divide-a-data-warehouse-into-layers)
- "Alibaba's data framework recommends structuring the data warehouse into three layers, from bottom to top: the Operational Data Store (ODS) layer, the Common Data Model (CDM) layer, and the Application Data Service (ADS) layer."
- ODS: "This layer stores raw data from source systems. Its structure mirrors that of the source system and serves as the data staging area ... ingest foundational data into MaxCompute and record its historical changes." "the ODS layer is divided into three parts: a data staging area, an offline data area, and a near-real-time data area."
- CDM: "processes data from the ODS layer, consists of the DIM, DWD, and DWS sub-layers. ... process and integrate data, establish conformed dimensions, build reusable detailed fact tables ..., and aggregate metrics at common granularities."
- DIM: "establishes conformed dimensions for the entire enterprise. ... Tables in the DIM layer are often called logical dimension tables, where each dimension typically corresponds to a single logical dimension table."
- DWS: "Driven by analytical subjects and the metric requirements ..., builds summary fact tables at a common granularity, materializing these models as wide tables. ... Tables in the DWS layer, known as summary logical tables, store derived metrics."
- DWD: "Driven by specific business processes, this layer builds detailed fact tables at the finest granularity. ... important dimension attributes can be denormalized into the fact tables to create wide tables. Tables in the DWD layer are often called logical fact tables."
- ADS: "stores customized statistical metrics for data products and applications, generated by processing data from the CDM and ODS layers."
- Flow: "Data from the ODS and DWD layers is published to data middleware for subscription by downstream services. Data from the DWS and ADS layers is typically stored in online storage systems, which downstream applications access via API calls."

## 11. Data access rules between warehouse layers  (specify-the-principles-for-using-data-at-different-layers)
Verbatim rules:
- "The ADS application layer should preferentially access data from the common layer of the data warehouse. If data already exists in the CDM layer, ADS must not bypass CDM and reprocess data from ODS."
- "Application-layer tasks must not reference ODS data directly. If the intermediate layer has not consolidated the required ODS data, access it through a view in the CDM layer. CDM views must be encapsulated in scheduled programs so that they remain maintainable and manageable."
- "CDM task chains should not be too deep. We recommend no more than 10 levels."
- "A computation and refresh task should output only one table, except in special cases."
- "If multiple tasks refresh and output to one table by writing to different partitions, create a virtual task in DataWorks that depends on the refresh and output of those tasks. Downstream tasks should generally depend on this virtual task."
- "The CDM summary layer should preferentially access the CDM detail layer when calculating additive metrics. Where possible, it should first use existing coarse-grained summaries instead of calculating large amounts of summary data directly from massive detail-layer datasets."
- "Cumulative snapshot fact tables in the CDM detail layer should preferentially access CDM transactional fact tables to maintain data consistency."
- "Build the CDM common summary layer for specific needs to prevent the application layer from relying excessively on CDM detail data."
- Also: "Avoid excessive references to ODS, unnecessary data copying, and redundant subsets."

## 12. Design a data model: empty container (children DIM, DWD, DWS).

## 13. Conformed dimension layer (DIM)  (dim-layer)
- "A dimension table is a physical table built on the data platform based on dimensions and their attributes, and it follows the design principles of a wide table."
- Uniqueness: "Company A's product dimension can have only one definition, and the `province code` dimension must convey the same information for any business process."
- Dimension table design rules (verbatim): "A single dimension table should contain no more than 10 million records." "When you join a dimension table with other tables, use a Map Join." "Avoid updating the data in dimension tables too frequently."
- Considerations: stability ("you can consider creating a single partition to store the full data. If some records are never updated, you might need to create separate history and daily tables. The daily table stores currently valid records ... The history table inserts records into corresponding partitions based on their deletion time."); vertical partitioning (split many/unused attribute columns into several dimension tables); horizontal splitting (clear record boundaries -> multiple tables or multi-level partitions); generation time of core dimension tables.
- Steps: define initial dimensions (ensure consistency); identify the primary dimension table ("usually an operation data store (ODS) table that syncs directly with the business system", e.g. `s_auction`); identify related dimension tables; define dimension attributes (from primary then related tables). Attribute guidance: "Generate rich dimension attributes." "Provide meaningful text descriptions." "Distinguish between numeric attributes and facts." "Try to establish common dimension attributes."
- NAMING (verbatim): "`dim_{business_segment_name/pub}_{dimension_definition}[_{custom_naming_label}]`. `pub` indicates a public dimension that is not specific to any business segment or is common to all business segments. The time dimension is a common example." Examples: "Public area dimension table dim_pub_area"; "Full product table for Company A's E-commerce segment dim_asale_itm".
- DDL examples: `dim_asale_itm` columns item_id BIGINT, item_title, item_price, item_stuff_status, cate_id, cate_name, commodity_id, commodity_name, umid, item_status, city, prov; `PARTITIONED BY (ds STRING COMMENT 'Date, yyyymmdd')`. `dim_pub_area` columns buyer_id, city_code, city_name, prov_code, prov_name; `PARTITIONED BY (ds STRING COMMENT 'Date partition in yyyymmdd format') LIFECYCLE 3600`.
- Not on this page: SCD types, surrogate keys, unknown member, role-playing, junk dimensions.

## 14. Data Warehouse Detail (DWD) layer  (data-warehouse-detail-layer)
- "The DWD layer retains the most atomic records". "To build wide tables, duplicate key dimension attributes directly into a fact table instead of always joining a separate dimension table. These stored dimension columns are called degenerate dimensions."
- Fact types: Additive "Sums correctly across any dimension" (Revenue, quantity); Semi-additive "Sums correctly across some dimensions, not all" (Inventory balance); Non-additive "Cannot be summed at all" (Ratios, percentages). "Decompose non-additive facts into their additive components before storing them. For example, store a ratio's numerator and denominator as separate additive columns."
- Fact table types: Transaction ("Stores the most atomic data; also called an atomic fact table"); Periodic snapshot ("Rows are inserted on a predictable schedule (daily, weekly)"); Accumulating snapshot ("Has multiple date columns for key milestones; rows are updated as the process progresses").
- Do: "Declare the statistic granularity before selecting dimensions or measures." "Include all measures relevant to a single business process in one fact table." "Store only measures at a single granularity per table." "Use the same unit for a measure across different fact tables." "Decompose non-additive facts into additive components." "Use degenerate dimensions to avoid unnecessary joins". "Handle null measure values explicitly—decide upfront whether to store zero, null, or a sentinel value."
- Don't: "Associate a fact table at the DWD layer with more than one dimension. Mixed-dimension tables make granularity ambiguous" (as written; semantics unclear). "Mix measures of different granularities in the same table."
- Four steps: select the business process -> declare the granularity -> select dimensions -> select measures.
- NAMING (verbatim): "dwd_{business_unit|pub}_{data_domain}_{business_process}[_{custom_tag}]_{partition_type}"; `dwd` fixed prefix; `{business_unit}` or `pub` "use pub when data spans multiple business units"; `{data_domain}` abbreviated (trd trade, itm item); `{business_process}` abbreviated; `{custom_tag}` optional; `{partition_type}`: "di for daily incremental, df for daily full". Examples: `dwd_asale_trd_ordcrt_trip_di` (air ticket orders, daily incremental), `dwd_asale_itm_item_df` (product snapshots, daily full).
- Tutorial tables: dwd_asale_trd_itm_di, dwd_asale_trd_ord_di, and a table listed as `ods_asale_trd_mbr_di` (sic, an ods_ name inside the DWD page). All "partitioned by date (ds) with a 400-day retention period": `PARTITIONED BY (ds STRING COMMENT 'Date') LIFECYCLE 400`. Column examples: item_id, buyer_id, order_id, pay_status, confirm_paid_amt, item_quantity, mord_prov, mord_city (degenerate dims embedded).

## 15. Common summary fact layer (DWS)  (data-warehouse-service-layer)
- "Each table in this layer typically contains at least one derived metric."
- Aggregation notes: "Aggregation summarizes data from the original star schema without combining data across different fact tables. The dimensions and measures ... must remain consistent with those in the original model so that queries return the same results." "Aggregation can significantly improve query performance, but it also makes ETL maintenance more complex."
- Principles: "Data reusability" (aggregate only along frequently used dimensions); "Keep data domains separate"; "Distinguish statistical periods: Table names must indicate the statistical period of the data. For example, _1d represents the last day, _td represents all historical data up to and including the current day, and _nd represents the last N days."
- NAMING (verbatim): "dws_{business_unit_abbreviation/pub}_{data_domain_abbreviation}_{data_granularity_abbreviation}[_{custom_table_name_tag_abbreviation}]_{statistical_period_range_abbreviation}"
- Period rules (verbatim): "By default, batch computation requires three tables for different statistical periods: the last day (_1d), the last N days (_nd), and all historical data up to and including the current day (_td). If the _nd table has too many columns and needs to be split, split it only by individual statistical period. For example, use a separate table for the last seven days (_1w). A table must not contain data for multiple statistical periods." "Use _hh for hourly tables, regardless of whether they are refreshed daily or hourly." "Use _mm for minute-level tables ..."
- Examples: dws_asale_trd_byr_subpay_1d, dws_asale_trd_byr_subpay_td, dws_asale_trd_byr_cod_nd, dws_asale_itm_slr_td, dws_asale_itm_slr_hh, dws_asale_itm_slr_mm.
- DDL: `dws_asale_trd_byr_ord_1d`, `dws_asale_trd_itm_ord_1d`; metric column `confirm_paid_amt_sum_1d` (atomic name + aggregation + period; no modifier prefix); `PARTITIONED BY (ds STRING COMMENT 'Partition column in YYYYMMDD format') LIFECYCLE 36000`.

## 16. Project assignment and security  (project-allocation-and-security)
- "the project granularity is determined by the data layer. For the ODS, CDM, and DWS layers, create projects based on business segments. For the application layer (ADS), create projects based on applications."
- Suffixes: "ods suffix ... asale_ods"; "cdm suffix ... asale_cdm"; ADS: "bi suffix ... asale_bi" for reports/analysis, "app suffix ... asale_app" for data-product applications.
- Standard mode: "one DataWorks project corresponds to two MaxCompute projects" (dev with `_dev` suffix + prod) to "prevent unauthorized operations on production tables". Roles control who edits/tests code, who publishes to production, resource usage. Defers to "Permission overview".

## 17. Establish a performance baseline  (performance-benchmark-establishment)
- "The performance of MaxCompute tables primarily depends on proper table design. ... establish a baseline before you start optimizing." Record per table: data synchronization time, storage usage, query execution time, estimated query charge (plus purchased quantity for subscription). Sync time from Operation Center > Cycle Examples; storage via `DESCRIBE`; query time/cost via DataStudio ODPS SQL node cost estimate (pay-as-you-go: "A fee of less than CNY 0.01 is rounded up to CNY 0.01"). Sample queries are `SELECT * FROM <ods table> WHERE ds=20190428`.

## 18. Data warehouse performance optimization  (data-warehouse-performance-optimization)
- "You can optimize data warehouse performance by optimizing tables and data distribution."
- Hash clustering: "use the clustered by clause to specify a Hash Key ... choose columns that have few repeat key values." `ALTER TABLE table_name [CLUSTERED BY (...) [SORTED BY (...)] INTO number_of_buckets BUCKETS]`; limitations: INSERT INTO unsupported (use INSERT OVERWRITE); no Tunnel upload into range cluster tables.
- Other: "Use intermediate tables for tables that have a large data volume and many downstream tasks." "Split tables. If individual fields are generated very slowly, split those fields into separate tables." "Merge tables. ... merge the tasks and data for tables with overlapping or duplicate business logic." "Zipper table: You can leverage zipper tables to reduce your storage consumption." (no zipper design detail given anywhere in the section)

## 19. Result validation  (result-verification)
- Validate after optimization; if schema changed, "delete the original table. Create a new table and partitions"; retest; record Data synchronization time, Storage size, Query running time, Estimated query cost, "compare it with the performance baseline". Validation here is performance-only, not data-correctness.

---
# Differences vs. our spec
Spec: `docs/en/specs/2026-11-04-kimball-dwh-design.md` (before the 2026-11-04 amendments; see its §11). Verdict key: DELIBERATE (spec decision), GAP (spec silent/weaker), ERROR-RISK (possible mistake), SOURCE-ODDITY.

1. Layer model. Alibaba (#10): three layers ODS / CDM(DIM,DWD,DWS) / ADS. Spec D2/§7 01-layers: five folders ods/dim/dwd/dws/ads. DELIBERATE (CDM is a grouping, same sub-layers).
2. Business-segment prefix. Alibaba (#13,#14,#15): `dim_{business_segment_name/pub}_...`, `dwd_{business_unit|pub}_{data_domain}_...`, `dws_{business_unit/pub}_{data_domain}_...`; project split by segment (#16). Spec D10 drops it. DELIBERATE. Side effect: spec `dim_{pub|domain}_{dimension}` puts the DOMAIN in the slot Alibaba reserves for the SEGMENT; the pub/segment concept becomes pub/domain. Flag in 02-naming (segment != domain, #2 glossary).
3. Partition column. Alibaba: `ds STRING` yyyymmdd (all DDL). Spec D10: `dt` DATE. DELIBERATE.
4. DWS period suffixes. Alibaba (#15): `_1d`, `_nd`, `_td`, `_1w` (split of nd), `_hh`, `_mm`; default is THREE tables (1d, nd, td); "A table must not contain data for multiple statistical periods". Spec §7 02: `_1d|nd|td`; §5 periods.yml: `1d,7d,30d,nd,td,1h`. GAP/ERROR-RISK: spec has no "one period per table" rule, no default 1d/nd/td triple, and its `7d`/`30d`/`1h` do not map to Alibaba's `_1w`/`_hh` tokens; define a single mapping (what is `nd` vs `30d`) in 02-naming/06-metrics.
5. Metric column naming. Alibaba (#15 DDL): `confirm_paid_amt_sum_1d` = atomic + aggregation + period. Spec §7 06: `{modifier}_{atomic}_{period}` e.g. `app_pay_amt_30d`. Alibaba conceptual formula is Period+Modifier+Atomic (#7) but gives no column template; spec's choice is its own. DELIBERATE-ish, [column template not from source]; note spec omits aggregation token (sum/cnt) that Alibaba's example has.
6. Calculated metrics. Alibaba (#2,#7) only atomic and derived. Spec §5 metrics.yml adds `calculated`. Spec addition [not from source]; fine, but should be stated as extension. Alibaba also says modifier types exist and "A modifier inherits the data domain from its modifier type", derived metric inherits domain from its atomic (not modifier); spec modifiers.yml has "applicable processes" and no modifier-type or domain inheritance. GAP (minor). Spec also puts grain inside the derived metric; Alibaba treats granularity as "often used as a modifier" (#2): DELIBERATE refinement.
7. "Modifier" vs "business filter". Alibaba #2 calls the filter "Business filter" (no time range), #7 uses "modifier". Spec modifiers.yml = business filters, consistent. OK.
8. Layer dependencies. Alibaba (#11): ADS must not read ODS directly (use a CDM view if needed); CDM chain depth <= 10; one task one table; virtual task when several tasks write partitions of one table; DWS reads DWD preferentially and should reuse coarser existing summaries; accumulating snapshot reads transaction facts; build DWS to stop ADS depending on DWD. Spec §7 01: ADS <- DWS (DWD allowed with written reason); DWS <- DWD+DIM; no upward reads; only ODS calls source(). Spec is stricter on ADS (OK, DELIBERATE) but GAP: no depth limit, no one-model-one-table note (dbt gives it), no "DWS may build on lower-grain DWS", no "accumulating snapshot reads transaction fact" rule, DIM<-ODS/DIM unspecified by Alibaba.
9. Dimension design. Alibaba (#13): <=10M rows per dim table, Map Join, avoid frequent updates, daily full-snapshot partition (`ds`) or history/daily split, vertical/horizontal splitting; zipper tables only mentioned as storage saver (#18). No SCD types, surrogate keys, -1 unknown member, role-playing or junk dimensions anywhere in the section. Spec §7 04 (hash surrogate keys, -1, SCD1 as df, SCD2 via snapshot with valid_from/valid_to/is_current, role-playing, junk) is Kimball content [not from source]; DELIBERATE addition. GAP the other way: spec has no row-count ceiling for DIM and no stability/splitting guidance (less relevant on Trino/Iceberg).
10. Degenerate dimension terminology. Alibaba (#14) uses "degenerate dimensions" for dimension ATTRIBUTES copied into the fact table (denormalised wide table). Spec §7 04 lists degenerate dimensions (Kimball sense: transaction ids) AND §7 05 "degenerating frequently used DIM attributes into DWD (Alibaba practice)". Terminology clash; recommend using different words in 04 vs 05.
11. Fact design. Alibaba (#14) three fact table types, additive/semi/non-additive, 4-step process (process, grain, dimensions, measures), decompose non-additive, same unit, explicit null policy, one grain per table. Spec §6/§5/05-facts matches (grain statement, types). GAP: spec does not list "same unit across fact tables" nor "null measure policy" nor "all measures of a process in one fact table". Alibaba's "Don't associate a fact table with more than one dimension" is unclear [SOURCE-ODDITY] and should not be copied.
12. DWD naming. Alibaba: `dwd_{business_unit|pub}_{data_domain}_{business_process}[_{custom_tag}]_{partition_type}`, partition_type di|df. Spec: `dwd_{domain}_{process}_{di|df}` = same minus segment, custom tag omitted. DELIBERATE (custom tag dropped; ok). Spec DWD has no accumulating-snapshot naming.
13. ODS naming. Alibaba gives NO ODS template in this section (only the stray `ods_asale_trd_mbr_di` inside the DWD page, source typo/oddity). Spec `ods_{source}_{table}_{di|df}` is spec-original [not from source]; Alibaba's ODS has staging/offline/near-real-time areas (#10) which the spec ignores (spec ODS = daily batch only). GAP (no near-real-time/ staging area), fine for scope.
14. ADS. Alibaba tutorial has no ADS page and no ADS name template; only role (#10), access rule (#11) and project split by application with `bi`/`app` suffix (#16). Spec `ads_{app}_{subject}_{period}` and "ADS serves one stated need and names its consumer" are spec-original [not from source]. Spec cites the Alibaba section as the basis, so do not attribute ADS naming to it.
15. Lifecycle / retention. Alibaba: explicit `LIFECYCLE n` on every table (DIM 3600, DWD 400, DWS 36000; units/values inconsistent in source). Spec has only "Iceberg maintenance (optimize, expire snapshots)" in 08, no per-layer data retention rule. GAP.
16. Project/security split. Alibaba (#16): separate MaxCompute projects per layer (ods/cdm; ADS per application with bi/app), dev/prod standard mode. Spec: no equivalent (single catalog/schemas, CI schema `ci_pr_<n>` in §8.1); infrastructure out of scope in §1. Likely DELIBERATE-by-scope but no access-control rule per layer exists in the spec. GAP (security/permissions by layer undocumented).
17. Performance baseline and validation. Alibaba (#17,#18,#19): baseline of sync time, storage, query time, est. cost before optimizing; hash clustering, intermediate/split/merge tables, zipper; re-measure and compare. Spec: `dwh-verify` checks row counts/reconciliation and Trino SQL style (10), "performance" is an operations class, but no baseline/before-after procedure and no Iceberg analogue (bucket/sort partition transforms, file compaction metrics). GAP. Note Alibaba's "Result validation" is performance-only; the spec's reconciliation checks (12-data-quality) go beyond the source.
18. Requirement/survey process. Alibaba (#3,#4,#5,#6,#7): investigate business -> requirement analysis document of atomic/derived metrics -> business processes -> data domains -> dimensions + bus matrix -> metrics (atomic before derived). Spec §6 skills `dwh-requirement` then `dwh-model-design` covers the same order and enforces "search for reusable concepts first". Consistent. Alibaba bus matrix cells are only Y/N; spec adds role names. DELIBERATE refinement. Alibaba domain partitioning by "department, business process, or functional module" and keep domains extensible; spec 03 should say the same.
19. Source inconsistencies to avoid copying: product condition coded 0/1/2 (DIM, DWD) vs 1/2/3 (bus matrix page); "Transaction Amount" listed as a bus-matrix dimension; `ods_asale_trd_mbr_di` listed as DWD; DWS lifecycle 36000 days; "product condition"/"Category ID" duplicated attribute names.
