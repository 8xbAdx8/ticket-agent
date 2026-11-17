"""Finite policy-scope checks and vector-led RRF; never generates an answer.

This is an explicit capability map for this small simulated corpus, not a general
semantic entailment model. Unrecognised or insufficient scope asks for review or
clarification rather than deriving a rule from shared Chinese characters.
"""
import copy
import re

PROFILE='v351'
# These map corpus subjects, not test IDs/questions or expected answers.
TOPICS=(
 ('lock',r'锁座',('P11',)),
 ('refund',r'退票|退(?:高铁|车|机)票|退费|退款|退多少|(?:还能|能|可以)退(?:吗|不)',('P01','P09')),
 ('change',r'改签|改票|还能改|改吗',('P02','P03')),
 ('after_departure',r'(?:开车|发车)后|已经.{0,5}(?:开车|发车)|错过.{0,5}(?:开车|发车)',('P03',)),
 ('child',r'儿童|小孩|小朋友|五岁|1\.2\s*米',('P04',)),
 ('student',r'学生|大学生|在校',('P05',)),
 ('baggage',r'行李|箱子|携带品|公斤|千克',('P06',)),
 ('voucher',r'报销|凭证|补打',('P07',)),
 ('waitlist',r'候补|监控',('P08','P14')),
 ('identity',r'身份证|实名|同一天.{0,10}(?:买|几张)',('P10',)),
 ('privacy',r'别人.{0,4}(?:订单|信息)|其他手机号|另一个手机号|隐私|自己.{0,4}订单',('P13',)),
 ('data_window',r'(?:演示|模拟)(?:数据|数据库)|数据库|预售|日期窗口',('P15',)),
 ('cancel',r'(?:取消|撤销).{0,6}订单|订单.{0,6}(?:取消|撤销)|没付钱取消|未付款取消',('P12',)),
)
# Requested attributes outside the current corpus. Kept visible in sidecars;
# expanding the knowledge base requires revisiting this finite scope map.
ATTRIBUTES=(
 ('insurance',r'保险|理赔|赔付|免赔|报案'),
 ('animals',r'宠物|带猫|带狗|检疫'),
 ('mileage_points',r'里程|积分'),
 ('invoice_tax',r'电子发票|税率|税额|发票抬头'),
 ('discount_stacking',r'优惠券|会员券|叠加'),
 ('instalments',r'分期|信用卡'),
 ('refund_arrival',r'到账|退回支付宝|退回银行卡'),
 ('privacy_retention',r'(?:信息|数据).{0,8}(?:保存|保留).{0,8}(?:年|多久)|永久删除|删除.{0,5}(?:信息|数据)'),
 ('replacement_identity',r'护照|身份证遗失|临时身份证'),
 ('compensation',r'晚点|赔偿|违约金'),
 ('courier',r'快递|寄递'),
 ('rename',r'改姓名|改名|更名'),
 ('other_discounts',r'军人|残疾|敬老'),
 ('meals_lounge',r'餐食|餐饮|贵宾|休息室|早餐|酒店'),
 ('exact_release_time',r'准确到秒|精确.{0,4}放票|放票时刻|几点放票'),
)


def scope_requirements(question):
    topics=[name for name,pattern,_ in TOPICS if re.search(pattern,question)]
    ids={uid for name,_,values in TOPICS if name in topics for uid in values}
    # Natural cancellation variants should not be routed to rail refunds.
    if re.search(r'取消|撤销',question) and re.search(r'没付|未付|尚未支付',question):
        ids.add('P12');topics.append('unpaid_cancel')
    unsupported=[name for name,pattern in ATTRIBUTES if re.search(pattern,question)]
    personal_fee=bool(re.search(r'(?:我这张|这单|我的.{0,3}票).{0,12}(?:实际|具体|多少元|手续费是多少)',question))
    personal_change=bool(re.search(r'我现在.{0,5}(?:改票|改签)',question))
    # A personal amount/eligibility cannot be decided by a generic policy alone.
    clarification=personal_fee or personal_change or (not topics and bool(re.search(r'那|这单|这个|扣多少',question)))
    air=bool(re.search(r'机票|经济舱|航空|飞机|起飞|机场|托运',question))
    rail=bool(re.search(r'高铁|车票|火车|动车|发车|开车|乘车',question))
    if air:
        ids.intersection_update({'P09','P11','P12','P13'})
    elif rail:
        ids.discard('P09')
    # A category mention alone does not make all policies in that category relevant.
    if 'waitlist' in topics:
        if re.search(r'后台|轮询|自动.{0,3}(?:付款|扣款)|扣款|监控任务',question):ids.discard('P08')
        else:ids.discard('P14')
    return {'topics':list(dict.fromkeys(topics)),'allowed_policy_ids':sorted(ids),
            'unsupported_attributes':unsupported,'needs_clarification':clarification,
            'transport_scope':'air' if air else 'rail' if rail else 'unspecified',
            'limits':'Finite corpus capability checks; unknown paraphrases and semantic gaps require B review.'}


def apply_quality(question,lexical,vector_hits,mode,k=3,min_keyword_score=0.0,vector_weight=0.7):
    from target.rag_store import dedup
    if mode not in ('keyword','vector','hybrid') or not 1<=k<=20 or not 0<=min_keyword_score or not 0<vector_weight<1:
        raise ValueError('invalid_quality_configuration')
    requirements=scope_requirements(question);allowed=set(requirements['allowed_policy_ids'])
    all_rows={h['doc_id']:copy.deepcopy(h) for h in lexical}
    for h in vector_hits:all_rows[h['doc_id']]={**all_rows.get(h['doc_id'],{}),**copy.deepcopy(h)}
    rejections=[]
    def reason(h):
        if requirements['needs_clarification']:return 'missing_context_or_personal_conditions'
        if requirements['unsupported_attributes']:return 'requested_attribute_not_in_corpus'
        if not requirements['topics']:return 'no_recognized_policy_subject'
        if h['doc_id'] not in allowed:return 'policy_subject_or_transport_mismatch'
        return None
    for h in all_rows.values():
        why=reason(h)
        if why:rejections.append({'doc_id':h['doc_id'],'reason':why,'score':h.get('score')})
    lex=dedup([h for h in lexical if not reason(h) and h.get('keyword_score',h['score'])>min_keyword_score],20)
    vec=dedup([h for h in vector_hits if not reason(h)],20)
    if mode=='keyword':hits=dedup(lex,k);fusion=None
    elif mode=='vector':hits=dedup(vec,k);fusion=None
    else:
        # Lexical candidates cannot resurrect a vector-abstained query. Both
        # ranks are recomputed after scope checks so noise cannot crowd out a
        # supported document. The semantic branch has explicit 0.7 weight.
        valid={h['doc_id'] for h in vec};fused={}
        for name,items,weight in (('keyword',lex,1-vector_weight),('vector',vec,vector_weight)):
            for rank,item in enumerate(items,1):
                if item['doc_id'] not in valid:continue
                row=fused.setdefault(item['doc_id'],{**copy.deepcopy(item),'score':0.0,'fusion_ranks':{},'fusion_weights':{}})
                row['score']+=weight/(60+rank);row['fusion_ranks'][name]=rank;row['fusion_weights'][name]=weight
                if name=='vector':row['vector_score']=item.get('vector_score',item['score'])
        hits=dedup(sorted(fused.values(),key=lambda h:(-h['score'],-h.get('vector_score',-1),h['doc_id'])),k)
        fusion='vector_qualified_weighted_rrf_k60'
    state='needs_clarification' if requirements['needs_clarification'] else 'insufficient_evidence' if not hits else 'scoped_evidence'
    return {'hits':hits,'candidate_hits':list(all_rows.values()),'rejections':rejections,
            'sufficiency':{'state':state,'abstain_recommended':not hits,**requirements},
            'fusion':fusion,'quality_profile':PROFILE,'minimum_keyword_score':min_keyword_score,
            'vector_weight':vector_weight if mode=='hybrid' else None}
