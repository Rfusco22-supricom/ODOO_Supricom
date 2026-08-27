odoo.define('@632971da7db6c645b0ada45222be7593b67278059796eba2a6c9b69b45acda99',['@web/core/utils/patch','@web/core/utils/hooks','@103c7d79cc526d077aeb6c0d794e9325b026ab588961f8ee74e08fcae5becbcb','@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef'],function(require){'use strict';let __exports={};const{patch}=require('@web/core/utils/patch')
const{useBus}=require('@web/core/utils/hooks')
const{ChatroomActionTab}=require('@103c7d79cc526d077aeb6c0d794e9325b026ab588961f8ee74e08fcae5becbcb')
const{ConversationModel}=require('@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef')
const SaleForm=__exports.SaleForm=class SaleForm extends ChatroomActionTab{setup(){super.setup()
this.env;this.props
useBus(this.env.chatBus,'productDragInit',()=>{this.elRef.el.classList.add('drop-active')})
useBus(this.env.chatBus,'productDragging',({x,y})=>{if(this.isInside(x,y)){this.elRef.el.classList.add('drop-hover')}else{this.elRef.el.classList.remove('drop-hover')}})
useBus(this.env.chatBus,'productDragEnd',()=>{this.elRef.el.classList.remove('drop-active')
this.elRef.el.classList.remove('drop-hover')})
useBus(this.env.chatBus,'productDrop',async({x,y,product})=>{if(this.isInside(x,y)&&this.props.selectedConversation?.isCurrent()){this.env.chatBus.trigger('chatroomAddToOrder',product)}})}
getExtraContext(props){const context=Object.assign(super.getExtraContext(props),{default_partner_id:props.selectedConversation.partner.id,})
if(props.selectedConversation.team.id){context['default_team_id']=props.selectedConversation.team.id}
return context}
async onSave(record){await super.onSave(record)
if(record.resId!==this.props.selectedConversation.sale.id){await this.env.services.orm.write(this.env.chatModel,[this.props.selectedConversation.id],{sale_order_id:record.resId},{context:this.env.context})
this.props.selectedConversation.updateFromJson({sale_order_id:[record.resId,record.data.name]})
this.env.chatBus.trigger('updateConversation',this.props.selectedConversation)}}
_getOnSearchChatroomDomain(){let domain=super._getOnSearchChatroomDomain()
domain.push(['conversation_id','=',this.props.selectedConversation.id])
if(this.props.selectedConversation.partner.id){domain.unshift('|')
domain.push(['partner_id','=',this.props.selectedConversation.partner.id])}
return domain}}
SaleForm.props=Object.assign({},SaleForm.props)
SaleForm.defaultProps=Object.assign({},SaleForm.defaultProps)
patch(SaleForm.props,{selectedConversation:{type:ConversationModel.prototype},viewModel:{type:String,optional:true},viewType:{type:String,optional:true},viewKey:{type:String,optional:true},})
patch(SaleForm.defaultProps,{viewModel:'sale.order',viewType:'form',viewKey:'sale_form',})
return __exports;});;
odoo.define('@b671e91bb53678d42f1daf4106332bc764bc90465e8fd7e23dee595096f31e8f',['@web/core/utils/patch','@42ffbf6224f23aacdf6b9a6289d4e396904ef6225cba7443d521319d2137e2b6'],function(require){'use strict';let __exports={};const{patch}=require('@web/core/utils/patch')
const{Chatroom}=require('@42ffbf6224f23aacdf6b9a6289d4e396904ef6225cba7443d521319d2137e2b6')
const chatroomSale={setup(){super.setup()
this.saleAllowed=false},getSubEnv(){const out=super.getSubEnv()
out.saleAllowed=()=>this.saleAllowed
return out},async willStart(){return Promise.all([super.willStart(),this.env.services.user.hasGroup('sales_team.group_sale_salesman').then(res=>{this.saleAllowed=res}),this.getSaleFormView().then(res=>{this.saleFormView=res})])},async getSaleFormView(){const{orm}=this.env.services
const data=await orm.call(this.env.chatModel,'check_object_reference',['_sale','acrux_whatsapp_sale_order_form_view'],{context:this.context})
return data[1]}}
patch(Chatroom.prototype,chatroomSale)
return __exports;});;
odoo.define('@32ecc8c256ae0091350dd8e2d61df3d02e13061a3062844560a628a40582f9ab',['@web/views/fields/formatters','@web/core/assets','@odoo/owl'],function(require){'use strict';let __exports={};const{formatMonetary}=require('@web/views/fields/formatters')
const{loadBundle}=require('@web/core/assets')
const{Component,onWillStart,useEffect,useRef,onWillUpdateProps,markup}=require('@odoo/owl')
const SaleIndicator=__exports.SaleIndicator=class SaleIndicator extends Component{setup(){super.setup()
this.env
this.canvasRef=useRef('canvas')
this.monthLastSaleData=null
this.htmlLastSale=null
this.chart=null
onWillStart(this.willStart.bind(this))
onWillUpdateProps(this.onWillUpdateProps.bind(this))
useEffect(()=>{this.renderChart()
return()=>{if(this.chart){this.chart.destroy()}}})}
async willStart(){await this.getPartnerIndicator(this.props)
await loadBundle('web.chartjs_lib')}
async onWillUpdateProps(nextProps){await this.getPartnerIndicator(nextProps)}
async getPartnerIndicator(props){const result=await this.env.services.orm.call('res.partner','get_chat_indicators',[[props.partnerId]],{context:this.env.context},)
if(result['6month_last_sale_data']){this.monthLastSaleData=result['6month_last_sale_data'];}
if(result['html_last_sale']){this.htmlLastSale=markup(result['html_last_sale'])}}
renderChart(){if(this.monthLastSaleData){const config=this._getBarChartConfig()
this.chart=new Chart(this.canvasRef.el,config)}}
_getBarChartConfig(){var data=[]
var backgroundColor=['#FFD8E1','#FFE9D3','#FFF3D6','#D3F5F5','#CDEBFF','#E6D9FF']
var borderColor=['#FF3D67','#FF9124','#FFD36C','#60DCDC','#4CB7FF','#A577FF']
var labels=[]
let data_param=this.monthLastSaleData
data_param[0].values.forEach(pt=>{data.push(pt.value)
labels.push(pt.label)})
return{type:'bar',data:{labels:labels,datasets:[{data:data,fill:'start',label:data_param[0].key,backgroundColor:backgroundColor,borderColor:borderColor,}]},options:{scales:{y:{display:false},},maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{enabled:true,intersect:false,position:'nearest',caretSize:0,callbacks:{label:(tooltipItem)=>{let label=tooltipItem.dataset.label||''
if(label){label+=': '}
label+=formatMonetary(tooltipItem.raw,{currencyId:this.env.getCurrency()})
return label}}},},elements:{line:{tension:0.000001}},},}}}
Object.assign(SaleIndicator,{template:'chatroom.SaleIndicator',props:{partnerId:Number}})
return __exports;});;
odoo.define('@dc4f0d88697ef04cf330aaae2f9e0998b42d63fdd99c2b6d9aca525143ff01aa',['@web/core/utils/patch','@web/core/l10n/translation','@af0df1a5affde864bfaca0edba19137ac4e7199f2cb7ae310c45d7b47aaac68b','@632971da7db6c645b0ada45222be7593b67278059796eba2a6c9b69b45acda99','@32ecc8c256ae0091350dd8e2d61df3d02e13061a3062844560a628a40582f9ab'],function(require){'use strict';let __exports={};const{patch}=require('@web/core/utils/patch')
const{_t}=require('@web/core/l10n/translation')
const{TabsContainer}=require('@af0df1a5affde864bfaca0edba19137ac4e7199f2cb7ae310c45d7b47aaac68b')
const{SaleForm}=require('@632971da7db6c645b0ada45222be7593b67278059796eba2a6c9b69b45acda99')
const{SaleIndicator}=require('@32ecc8c256ae0091350dd8e2d61df3d02e13061a3062844560a628a40582f9ab')
const chatroomSaleTab={setup(){super.setup()
this.emptyPartnerMsg=_t('This conversation does not have a partner.')},get tabSaleFormProps(){return{viewTitle:_t('Order'),viewResId:this.props?.selectedConversation?.sale?.id,selectedConversation:this.props?.selectedConversation,searchButton:true,viewId:this.props.saleFormView,}},get titles(){const out=super.titles
out.tab_order=_t('Order')
return out}}
patch(TabsContainer.prototype,chatroomSaleTab)
patch(TabsContainer.components,{SaleForm,SaleIndicator,})
patch(TabsContainer.props,{saleFormView:{type:Number,optional:true},})
return __exports;});;
odoo.define('@094d8ecf596063d29aaf300ee5d932cb5c1f033cb570e636cba5aebbf986e346',['@web/core/utils/patch','@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef'],function(require){'use strict';let __exports={};const{patch}=require('@web/core/utils/patch')
const{ConversationModel}=require('@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef')
const chatroomSale={constructor(comp,base){super.constructor(comp,base)
this.sale={id:false,name:''}},updateFromJson(base){super.updateFromJson(base)
if('sale_order_id'in base){this.sale=this.convertRecordField(base.sale_order_id)}}}
patch(ConversationModel.prototype,chatroomSale)
return __exports;});;
odoo.define('@a724fcbfc24204ab570d7c1acd0ccfedc584b7f0575156f45bd704f9108d5bdc',['@web/views/form/form_renderer','@web/core/utils/hooks'],function(require){'use strict';let __exports={};const{FormRenderer}=require('@web/views/form/form_renderer')
const{useBus}=require('@web/core/utils/hooks')
const SaleFormRenderer=__exports.SaleFormRenderer=class SaleFormRenderer extends FormRenderer{setup(){super.setup()
useBus(this.env.chatBus,'chatroomAddToOrder',async product=>{const context={...this.env.services.user.context,default_product_id:parseInt(product.id)}
const newLine=await this.props.record.data.order_line.addNew({context,mode:'edit',position:'bottom',})
await newLine.switchMode('readonly')})}}
return __exports;});;
odoo.define('@977bb89d9bc10ec30edfc528d73c0b889b6ff0421ab6669d0b8feb4ff3d14904',['@web/core/registry','@web/views/form/form_view','@a724fcbfc24204ab570d7c1acd0ccfedc584b7f0575156f45bd704f9108d5bdc'],function(require){'use strict';let __exports={};const{registry}=require('@web/core/registry')
const{formView}=require('@web/views/form/form_view')
const{SaleFormRenderer}=require('@a724fcbfc24204ab570d7c1acd0ccfedc584b7f0575156f45bd704f9108d5bdc')
const SaleFormView=__exports.SaleFormView={...formView,Renderer:SaleFormRenderer,}
registry.category('views').add('acrux_whatsapp_sale_order',SaleFormView)
return __exports;});;
