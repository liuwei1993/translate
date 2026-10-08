cmake_minimum_required(VERSION 3.5.0)
project(pura70mt)

set(ORT_LIB ${CMAKE_CURRENT_SOURCE_DIR}/../../../oh_modules/sherpa_onnx/libs/${OHOS_ARCH}/libonnxruntime.so)
if(NOT EXISTS ${ORT_LIB})
    message(FATAL_ERROR "onnxruntime library not found: ${ORT_LIB}")
endif()

add_library(mt SHARED marian.cpp mt_napi.cpp)
target_include_directories(mt PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/third_party)
target_compile_features(mt PRIVATE cxx_std_17)
target_link_libraries(mt PUBLIC ${ORT_LIB} libace_napi.z.so)
