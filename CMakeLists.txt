cmake_minimum_required( VERSION 3.10 )

project( CoopHou )

list( APPEND CMAKE_PREFIX_PATH "$ENV{HFS}/toolkit/cmake" )
find_package( Houdini REQUIRED )


add_library( CoopHou SHARED
	src/main.cpp
    src/utils.cpp
    src/utils.h
    src/event_manager.cpp
    src/event_manager.h
)

target_link_directories( CoopHou PRIVATE "$ENV{HFS}/custom/houdini/dsolib" )

target_link_libraries( CoopHou PUBLIC Houdini zdll  )

houdini_configure_target( CoopHou )
