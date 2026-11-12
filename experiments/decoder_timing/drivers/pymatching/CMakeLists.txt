cmake_minimum_required(VERSION 3.18)
project(pm_timing CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# PyMatching pinned to the same release as the installed wheel (record in ENVIRONMENT.md).
set(PYMATCHING_GIT_TAG "v2.4.0" CACHE STRING "PyMatching git tag")
include(FetchContent)
FetchContent_Declare(pymatching
  GIT_REPOSITORY https://github.com/oscarhiggott/PyMatching.git
  GIT_TAG ${PYMATCHING_GIT_TAG}
  GIT_SHALLOW FALSE)
FetchContent_MakeAvailable(pymatching)

add_executable(pm_timing pm_timing.cc)
# Same optimisation flags as the PyMatching release build (-O3 -mno-avx2).
target_compile_options(pm_timing PRIVATE -O3 -mno-avx2)
target_include_directories(pm_timing PRIVATE ${pymatching_SOURCE_DIR}/src)
target_link_libraries(pm_timing PRIVATE libpymatching libstim)
target_link_options(pm_timing PRIVATE -pthread)
