#include <catch.hpp>

#include <sstream>
#include <mockturtle/algorithms/emap.hpp>
#include <mockturtle/io/genlib_reader.hpp>
#include <mockturtle/io/write_verilog.hpp>
#include <mockturtle/networks/aig.hpp>
#include <mockturtle/utils/tech_library.hpp>

using namespace mockturtle;

TEST_CASE( "map and write constant outputs without constant cells", "[write_verilog][emap]" )
{
  std::vector<gate> gates;
  std::istringstream in( "GATE inv 1 Y=!a; PIN * INV 1 999 1 0 1 0\n"
                         "GATE nand2 2 Y=!(a*b); PIN * INV 1 999 1 0 1 0\n" );
  REQUIRE( lorina::read_genlib( in, genlib_reader( gates ) ) == lorina::return_code::success );
  tech_library<3> lib( gates );
  aig_network aig;
  aig.create_po( aig.get_constant( false ) );
  aig.create_po( aig.get_constant( true ) );
  aig.create_po( aig.get_constant( true ) );

  emap_stats st;
  auto klut = emap_klut( aig, lib, {}, &st );
  REQUIRE_FALSE( st.mapping_error );
  std::ostringstream out;
  write_verilog_with_binding( klut, out );
  CHECK( out.str() == "module top( y0 , y1 , y2 );\n"
                      "  output y0 , y1 , y2 ;\n"
                      "  assign y0 = 1'b0 ;\n"
                      "  assign y1 = 1'b1 ;\n"
                      "  assign y2 = 1'b1 ;\n"
                      "endmodule\n" );

  auto block = emap( aig, lib, {}, &st );
  REQUIRE_FALSE( st.mapping_error );
  std::ostringstream block_out;
  write_verilog_with_cell( block, block_out );
  CHECK( block_out.str() == out.str() );
}
