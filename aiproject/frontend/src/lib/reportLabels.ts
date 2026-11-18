export const projectLabels:Record<string,string>={
  sg_junior:'新加坡初中升学',sg_senior:'新加坡高中或同等学历升学',sg_hospitality:'新加坡酒店就业班',
  sg_aviation:'新加坡航空就业班',sg_top_up:'新加坡专升本',sg_masters:'新加坡本升硕',de_vocational:'德国双元制',
}
export const complaintCategoryLabels:Record<string,string>={learning:'学习类',company:'公司服务类'}
export const featureLabels:Record<string,Record<string,string>>={
  intended_project:projectLabels,
  intended_country:{Germany:'德国',Singapore:'新加坡'},
  education_level:{junior_secondary:'初中',senior_secondary:'高中',vocational_secondary:'中职',college:'大专',bachelor:'本科',postgraduate:'研究生',other:'其他'},
  source_channel:{website:'官网'},
}
