cmake_minimum_required(VERSION 3.18)
project(cb_timing CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# Chromobius pinned to the installed wheel's release; it fetches its own Stim and PyMatching.
set(CHROMOBIUS_GIT_TAG "v1.1.1" CACHE STRING "Chromobius git tag")
include(FetchContent)
FetchContent_Declare(chromobius
  GIT_REPOSITORY https://github.com/quantumlib/chromobius.git
  GIT_TAG ${CHROMOBIUS_GIT_TAG}
  GIT_SHALLOW FALSE)
FetchContent_MakeAvailable(chromobius)

add_executable(cb_timing cb_timing.cc)
target_compile_options(cb_timing PRIVATE -O3)
target_include_directories(cb_timing PRIVATE ${chromobius_SOURCE_DIR}/src)
target_link_libraries(cb_timing PRIVATE libchromobius libpymatching libstim)
target_link_options(cb_timing PRIVATE -pthread)
