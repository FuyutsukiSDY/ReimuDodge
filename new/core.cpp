#include <cmath>
#include <algorithm>
#include "shooting.hpp"
extern "C" __declspec(dllexport) int shot(long long frame,int enabled,long long* pressed,long long* until){
 Shooting s;if(*pressed>=0)s.pressed=*pressed;s.releaseUntil=*until;bool r=s.wanted(frame,enabled);*pressed=s.pressed.value_or(-1);*until=s.releaseUntil;return r;
}
extern "C" __declspec(dllexport) void sweep(int n,int m,const double*p,const double*v,const double*b,double dt,double now,double r,double margin,double*out){
 for(int i=0;i<n;i++){double best=INFINITY;
 for(int j=0;j<m;j++){auto h=b+5*j;double x=p[i*2]-(h[0]+h[2]*now),y=p[i*2+1]-(h[1]+h[3]*now),u=v[i*2]-h[2],w=v[i*2+1]-h[3];
 double t=std::clamp(-(x*u+y*w)/std::max(u*u+w*w,1e-9),0.,dt);x+=u*t;y+=w*t;double gap=std::sqrt(x*x+y*y)-h[4]-r-margin;if(std::isnan(gap)){best=gap;break;}best=std::min(best,gap);}
 out[i]=m?best:1e4;}
}
