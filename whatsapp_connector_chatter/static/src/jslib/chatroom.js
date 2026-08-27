odoo.define('@a4ebddf1097c2cf3e9d4183edec46e00b7fa350b7728df711030228bea35b174',['@mail/core/web/chatter','@web/core/utils/patch','@odoo/owl','@d68a026058b022ff11bca00cf4e8955cba72cec01425e1d73f378af00de5ae8e'],function(require){'use strict';let __exports={};const{Chatter}=require('@mail/core/web/chatter')
const{patch}=require('@web/core/utils/patch')
const{useState,onWillStart}=require('@odoo/owl')
const{ChatterChatroom}=require('@d68a026058b022ff11bca00cf4e8955cba72cec01425e1d73f378af00de5ae8e')
patch(Chatter.prototype,{setup(){super.setup()
this.chatroomState=useState({chatroomInChatter:false})
onWillStart(async()=>{const group='whatsapp_connector_chatter.group_chat_in_chatter'
this.chatroomState.chatroomInChatter=await this.env.services.user.hasGroup(group)})},get isChatroomInstalled(){return true},get isInAcruxChatroom(){const controller=this.env.services.action.currentController
return controller?.action?.tag==='acrux.chat.conversation_tag'},get chatroomInChatter(){return this.chatroomState.chatroomInChatter},})
patch(Chatter.components,{ChatterChatroom})
return __exports;});;
odoo.define('@d68a026058b022ff11bca00cf4e8955cba72cec01425e1d73f378af00de5ae8e',['@42ffbf6224f23aacdf6b9a6289d4e396904ef6225cba7443d521319d2137e2b6','@0ac266676776f61364330bb041a16d836d8b315459e04c1a3381740f295958c7','@717da89923407d2bbdeadd4f99b9e8918889493cac89cdeb293e1e42f46b02fa','@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef','@odoo/owl','@web/core/utils/hooks'],function(require){'use strict';let __exports={};const{Chatroom}=require('@42ffbf6224f23aacdf6b9a6289d4e396904ef6225cba7443d521319d2137e2b6')
const{Conversation}=require('@0ac266676776f61364330bb041a16d836d8b315459e04c1a3381740f295958c7')
const{ConversationThread}=require('@717da89923407d2bbdeadd4f99b9e8918889493cac89cdeb293e1e42f46b02fa')
const{ConversationModel}=require('@e71c685495b3fd5a77d050fe9a0ee4564da20c118bd360ce54260886e1bb13ef')
const{Component,EventBus,useSubEnv,useState,onWillStart,useRef,onWillUpdateProps}=require('@odoo/owl')
const{useBus}=require('@web/core/utils/hooks')
const ChatterChatroom=__exports.ChatterChatroom=class ChatterChatroom extends Component{setup(){super.setup()
this.env;this.chatroom=Chatroom
this.state=useState(this.getInitState())
this.showUserInMessage=false
this.currencyId=null
this.modelsUsedFields={}
this.readFromChatroom={}
this.getCurrency=async(...args)=>this.chatroom.prototype.getCurrency.apply(this,args)
this.buildModelBuildDict=(...args)=>this.chatroom.prototype.buildModelBuildDict.apply(this,args)
this.buildBatchRequester=(...args)=>this.chatroom.prototype.buildBatchRequester.apply(this,args)
this._sendBatchResolver=(...args)=>this.chatroom.prototype._sendBatchResolver.apply(this,args)
this._groupMessageResult=(...args)=>this.chatroom.prototype._groupMessageResult.apply(this,args)
this.chatroomRef=useRef('chatroomRef')
useSubEnv(this.getSubEnv())
useBus(this.env.chatBus,'selectConversation',this.selectConversation)
onWillStart(this.willStart.bind(this))
onWillUpdateProps(this.willUpdateProps.bind(this))}
getInitState(){return{selectedConversation:null,conversations:[],active:true,}}
getSubEnv(){return{context:{},chatBus:new EventBus(),chatModel:'acrux.chat.conversation',getCurrency:()=>this.currencyId,getShowUser:()=>this.showUserInMessage,canTranscribe:()=>this.canTranscribe,canTranslate:()=>this.canTranslate,getCurrentLang:()=>this.currentLang,isVerticalView:()=>this.state.user?.tabOrientation==='vertical',isAdmin:()=>this.isAdmin,modelsUsedFields:this.modelsUsedFields,readFromChatroom:this.readFromChatroom,conversationBuildDict:this.buildModelBuildDict('acrux.chat.conversation','build_dict'),messageBuildDict:this.buildModelBuildDict('acrux.chat.message','search_read_from_chatroom',this._groupMessageResult),}}
async willStart(){this.currencyId=await this.getCurrency()
this.showUserInMessage=await this.env.services.user.hasGroup('whatsapp_connector.group_chat_show_user_in_message')
await this.chatroom.prototype.loadModelsUsedFields.apply(this)
await this.willUpdateProps(this.props)}
async willUpdateProps(nextProps){this.state.conversations=await this.getServerConversation(nextProps)
if(this.state.conversations.length){await this.selectConversation({detail:{conv:this.state.conversations[0]}})}else{await this.selectConversation({detail:{conv:null}})}}
async getServerConversation(props){const{orm}=this.env.services
let data=[]
if(props.thread?.model==='acrux.chat.conversation'){if(props.thread.id){data=await orm.call(this.env.chatModel,'build_dict',[[props.thread.id],22],{context:this.env.context})}}else{const partnerId=this.chatroomPartner(props)
if(partnerId){data=await orm.call(this.env.chatModel,'search_conversation_by_partner',[partnerId,22],{context:this.env.context})}}
return Promise.all(data.map(async conv=>{const con=new ConversationModel(this,conv)
await con.buildExtraObj()
return con}))}
async selectConversation({detail:{conv}}){this.state.selectedConversation=conv}
chatroomPartner(props){let out=null
if(props.thread?.model==='res.partner'){out=props.thread.id}else if(props.thread?.model){if(props.webRecord?.data?.partner_id){const partner=props.webRecord.data.partner_id
if(Array.isArray(partner)&&partner.length){out=partner[0]}}}
return out}}
Object.assign(ChatterChatroom,{props:{thread:Object,webRecord:Object,},components:{Conversation,ConversationThread,},template:'chatter.Chatroom',})
return __exports;});;
