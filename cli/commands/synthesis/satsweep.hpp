/* mockturtle: C++ logic network library
 * Copyright (C) 2018-2024  EPFL
 *
 * Permission is hereby granted, free of charge, to any person
 * obtaining a copy of this software and associated documentation
 * files (the "Software"), to deal in the Software without
 * restriction, including without limitation the rights to use,
 * copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following
 * conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
 * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 */

/*!
  \file satsweep.hpp
  \brief Functional reduction command

  \author Philippe Sauter
*/

#pragma once

#include <alice/alice.hpp>

#include <mockturtle/views/names_view.hpp>
#include <mockturtle/algorithms/functional_reduction.hpp>

namespace alice
{

class satsweep_command : public alice::command
{
private:
  mockturtle::functional_reduction_params ps;
  std::string pattern_if;
  std::string pattern_of;

public:
  explicit satsweep_command( const environment::ptr& env )
      : command( env,
                 "Performs functional reduction." )
  { 
    add_option( "--iterations", ps.max_iterations, "Max number of iterations. (0 = until no improvements) [default = 10]" );
    add_option( "--fanin-nodes", ps.max_TFI_nodes, "Max numer of nodes in transitive fanin cone. [default = 1000]" );
    add_option( "--fanout-limit", ps.skip_fanout_limit,"Max number of explored fanouts of TFI nodes. [default = 100]" );
    add_option( "--conflict-limit", ps.conflict_limit,"Conflict limit for the SAT solver. [default = 100]" );
    add_option( "--max-clauses", ps.max_clauses, "Maximum number of clauses of the SAT solver. [default = 1000]" );
    add_option( "--pattern-input", pattern_if, "Use patterns from file instead of random. [default = no]" );
    add_option( "--pattern-output", pattern_of, "Save appended patterns (with CEXs) into file. [default = no]" );
    add_option( "--num-patterns", ps.num_patterns, "Initial number of (random) simulation patterns. [default = 256]" );
    add_option( "--max-patterns", ps.max_patterns, "Max number of simulation patterns. Random re-seeding when exceeded. [default = 1024]" );
    add_flag( "--verbose,-v", "Toggle verbose printout [default = no]" );
  }

protected:
  void execute()
  {
    if ( store<network_manager>().empty() )
    {
      env->err() << "Empty logic network.\n";
      return;
    }

    if( !pattern_if.empty() )
      ps.pattern_filename = pattern_if;
    if( !pattern_of.empty() )
      ps.save_patterns = pattern_of;
    ps.verbose = is_set( "verbose" );
    
    network_manager& ntk = store<network_manager>().current();
    switch (ntk.get_current_type())
    {
      case AIG:
        mockturtle::functional_reduction( ntk.get_aig(), ps );
        break;

      case XAG:
        mockturtle::functional_reduction( ntk.get_xag(), ps );
        break;

      case MIG:
        mockturtle::functional_reduction( ntk.get_mig(), ps );
        break;

      case XMG:
        mockturtle::functional_reduction( ntk.get_xmg(), ps );
        break;

      case KLUT:
      case MAPPED:
      default: 
        env->err() << "[e] Network type is not supported by balance.\n";
        break;
    }
  }
};

ALICE_ADD_COMMAND( satsweep, "Synthesis" );

} // namespace alice