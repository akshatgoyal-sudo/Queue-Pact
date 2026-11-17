// Rendering only. Plot data and all calculations remain in Python.
export default {
  template: '<div></div>', props: {options:Object},
  async mounted() {
    const {Plotly}=await import('nicegui-plotly');
    if(this.disposed)return;
    this.plotly=Plotly;
    this.observer=new ResizeObserver(()=>this.update());
    this.observer.observe(this.$el);
    this.update();
  },
  beforeUnmount(){this.disposed=true;this.observer?.disconnect();if(this.plotly)this.plotly.purge(this.$el);},
  data(){return {plotly:null,observer:null,disposed:false,busy:false,again:false,lastWidth:0,lastOptions:null};},
  methods:{
    async update(){
      if(!this.plotly||this.disposed)return;
      if(this.busy){this.again=true;return;}
      const width=this.$el.clientWidth;
      if(!this.$el.isConnected||!this.$el.getClientRects().length||width<=0)return;
      if(this.lastWidth===width&&this.lastOptions===this.options)return;
      this.busy=true;
      try{
        const options=this.options;
        await this.plotly.react(this.$el,options.data||[],{...options.layout,width},
          {...options.config,responsive:false,displaylogo:false});
        this.lastWidth=width;this.lastOptions=options;
      }finally{
        this.busy=false;
        if(this.again){this.again=false;this.update();}
      }
    }
  }
};
