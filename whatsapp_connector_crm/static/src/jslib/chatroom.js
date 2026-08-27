odoo.define('@576697edb76c12d5c8672584cddd827493e7bb605cc69eb19e16727925c3d3f1',['@web/core/utils/patch','@103c7d79cc526d077aeb6c0d794e9325b026ab588961f8ee74e08fcae5becbcb','@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef'],function(require){'use strict';let __exports={};const{patch}=require('@web/core/utils/patch')
const{ChatroomActionTab}=require('@103c7d79cc526d077aeb6c0d794e9325b026ab588961f8ee74e08fcae5becbcb')
const{ConversationModel}=require('@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef')
const CrmLeadForm=__exports.CrmLeadForm=class CrmLeadForm extends ChatroomActionTab{setup(){super.setup()
this.env;this.props}
getExtraContext(props){const context=Object.assign(super.getExtraContext(props),{default_partner_id:props.selectedConversation.partner.id,default_mobile:props.selectedConversation.numberFormat,default_phone:props.selectedConversation.numberFormat,default_name:`${props.selectedConversation.connector.name}: ${props.selectedConversation.name}`,default_contact_name:props.selectedConversation.name,default_user_id:this.env.services.user.userId,})
if(props.selectedConversation.team.id){context['default_team_id']=props.selectedConversation.team.id}
return context}
async onSave(record){await super.onSave(record)
if(record.resId!==this.props.selectedConversation.lead.id){await this.env.services.orm.write(this.env.chatModel,[this.props.selectedConversation.id],{crm_lead_id:record.resId},{context:this.env.context})
this.props.selectedConversation.updateFromJson({crm_lead_id:[record.resId,record.data.display_name]})
this.env.chatBus.trigger('updateConversation',this.props.selectedConversation)}}
_getOnSearchChatroomDomain(){let domain=super._getOnSearchChatroomDomain()
domain.push(['conversation_id','=',this.props.selectedConversation.id])
if(this.props.selectedConversation.partner.id){domain.unshift('|')
domain.push(['partner_id','=',this.props.selectedConversation.partner.id])}
return domain}}
CrmLeadForm.props=Object.assign({},CrmLeadForm.props)
CrmLeadForm.defaultProps=Object.assign({},CrmLeadForm.defaultProps)
patch(CrmLeadForm.props,{selectedConversation:{type:ConversationModel.prototype},viewModel:{type:String,optional:true},viewType:{type:String,optional:true},viewKey:{type:String,optional:true},})
patch(CrmLeadForm.defaultProps,{viewModel:'crm.lead',viewType:'form',viewKey:'crm_form',})
return __exports;});;
odoo.define('@da89557c22a065921b559848c6d4f6e69cb066c318e9f1d190890e1bc88fb9d1',['@web/core/utils/patch','@web/core/l10n/translation','@af0df1a5affde864bfaca0edba19137ac4e7199f2cb7ae310c45d7b47aaac68b','@576697edb76c12d5c8672584cddd827493e7bb605cc69eb19e16727925c3d3f1'],function(require){'use strict';let __exports={};const{patch}=require('@web/core/utils/patch')
const{_t}=require('@web/core/l10n/translation')
const{TabsContainer}=require('@af0df1a5affde864bfaca0edba19137ac4e7199f2cb7ae310c45d7b47aaac68b')
const{CrmLeadForm}=require('@576697edb76c12d5c8672584cddd827493e7bb605cc69eb19e16727925c3d3f1')
const chatroomCrmLeadTab={get tabCrmLeadFormProps(){return{viewTitle:_t('CRM'),viewResId:this.props?.selectedConversation?.lead?.id,selectedConversation:this.props?.selectedConversation,searchButton:true,}},get titles(){const out=super.titles
out.tab_crm_lead=_t('CRM')
return out}}
patch(TabsContainer.prototype,chatroomCrmLeadTab)
patch(TabsContainer.components,{CrmLeadForm,})
return __exports;});;
odoo.define('@2e55e6e145857aeeb31103e6c01fc409cbce30a46d44a27114ce5bc5c2881088',['@web/core/utils/patch','@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef'],function(require){'use strict';let __exports={};const{patch}=require('@web/core/utils/patch')
const{ConversationModel}=require('@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef')
const chatroomCrm={constructor(comp,base){super.constructor(comp,base)
this.lead={id:false,name:''}},updateFromJson(base){super.updateFromJson(base)
if('crm_lead_id'in base){this.lead=this.convertRecordField(base.crm_lead_id)}}}
patch(ConversationModel.prototype,chatroomCrm)
return __exports;});;
