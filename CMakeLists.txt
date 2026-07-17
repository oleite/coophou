cmake_minimum_required(VERSION 3.21)

project(CoopHou LANGUAGES CXX)

# ==============================================================================
# Global settings
# ==============================================================================

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# GoogleTest should use the same runtime library as Houdini (/MD)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")

# Nice folder organization in Visual Studio
set_property(GLOBAL PROPERTY USE_FOLDERS ON)

# ==============================================================================
# Houdini
# ==============================================================================

list(APPEND CMAKE_PREFIX_PATH "$ENV{HFS}/toolkit/cmake")
find_package(Houdini REQUIRED)

# ==============================================================================
# CoopHou Core Library
# ==============================================================================

add_library(CoopHouCore STATIC
    src/event_manager.cpp
    src/utils.cpp
    src/watcher.cpp

    # Headers (optional, but nice for IDEs)
    src/event_manager.h
    src/utils.h
    src/watcher.h
)

target_include_directories(CoopHouCore
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(CoopHouCore
    PUBLIC
        Houdini
        Houdini::Dep::Qt6Core
        Houdini::Dep::Qt6Gui
        Houdini::Dep::Qt6Widgets
)

# ==============================================================================
# Houdini Plugin
# ==============================================================================

add_library(CoopHou SHARED
    src/main.cpp
)

target_link_libraries(CoopHou
    PRIVATE
        CoopHouCore
)

houdini_configure_target(CoopHou)

# ==============================================================================
# Tests
# ==============================================================================

include(CTest)

if(BUILD_TESTING)

    include(FetchContent)

    FetchContent_Declare(
        googletest
        GIT_REPOSITORY https://github.com/google/googletest.git
        GIT_TAG v1.15.2
    )

    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)

    FetchContent_MakeAvailable(googletest)

    add_executable(CoopHou_Tests
        tests/test_main.cpp
        tests/houdini_fixture.cpp
        tests/test_event_manager.cpp
    )

    target_include_directories(CoopHou_Tests
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/tests
    )

    target_link_libraries(CoopHou_Tests
        PRIVATE
            CoopHouCore
            GTest::gtest
    )

    include(GoogleTest)
    gtest_discover_tests(CoopHou_Tests
        DISCOVERY_MODE PRE_TEST
    )
endif()