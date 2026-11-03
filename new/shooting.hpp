#pragma once
#include <cstdint>
#include <optional>
struct Shooting {
 std::optional<std::int64_t> pressed; std::int64_t releaseUntil=-1;
 void reset(){pressed.reset();releaseUntil=-1;}
 bool wanted(std::int64_t frame,bool enabled){
  if(!enabled){reset();return false;}
  if(frame<releaseUntil)return false;
  if(!pressed||frame<*pressed)pressed=frame;
  if(frame-*pressed>=45){releaseUntil=frame+2;pressed.reset();return false;}
  return true;
 }
};
